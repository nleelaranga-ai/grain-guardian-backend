import math
import os
from typing import List
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(
    title="GrainGuardian Enterprise Core Analytical Decision Suite",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get("DATABASE_URL")

class AnalysisRequest(BaseModel):
    lot_id: str
    moisture: float = Field(..., ge=5.0, le=35.0)
    temperature: float = Field(..., ge=0.0, le=70.0)
    humidity: float = Field(..., ge=10.0, le=100.0)

class ClpEngineStatus(BaseModel):
    clp_moisture_violation: bool
    clp_temp_violation: bool
    clp_humidity_violation: bool
    clp_duration_violation: bool
    clp_fungal_violation: bool

class AnalysisResponse(BaseModel):
    record_id: str
    grain_health_index: int
    fungal_risk_status: str
    biological_activity_index: float
    projected_weight_loss_kg: float
    estimated_financial_loss_inr: float
    clp_matrix: ClpEngineStatus
    action_advisory: List[str]

def connect_to_database_pooler():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="Database Context Target URL Missing Environment Variables.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

@app.post("/api/v3/analyze", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
def process_harvest_telemetry_matrix(payload: AnalysisRequest):
    conn = connect_to_database_pooler()
    cursor = conn.cursor()
    
    try:
        # 1. Fetch system baseline settings limits relative to dynamic profiles
        cursor.execute("SELECT * FROM crop_profiles WHERE crop_name = 'Paddy (Rice - Fine)' LIMIT 1;")
        profile = cursor.fetchone()
        
        if not profile:
            # Fallback mock configuration parameters if structural records table hasn't been seeded yet
            profile = {
                'profile_id': 'dd7e099a-75d2-49c9-957d-15b3ae0441a4',
                'base_msp_per_kg': 23.20,
                'critical_moisture_threshold': 16.0,
                'warning_moisture_threshold': 14.5,
                'critical_temp_threshold': 42.0,
                'warning_temp_threshold': 35.0,
                'critical_humidity_threshold': 75.0,
                'max_safe_storage_days': 180
            }

        # 2. Process Henderson Biological Activity Curve Math Matrix
        bai = float(((payload.moisture / 13.5) ** 2) * (payload.temperature / 28.0))
        fungal_risk = "HIGH" if bai > 1.30 else ("MEDIUM" if bai > 1.05 else "LOW")

        # Evaluate 5-Stage CLP violations markers
        clp_m = payload.moisture > float(profile['critical_moisture_threshold'])
        clp_t = payload.temperature > float(profile['critical_temp_threshold'])
        clp_h = payload.humidity > float(profile['critical_humidity_threshold'])
        clp_d = False # Context tracking fallback marker
        clp_f = fungal_risk == "HIGH"

        # 3. Compute Composite Health Score weighted degradation steps
        m_penalty = max(0.0, ((payload.moisture - 14.5) / 1.5) * 100) if payload.moisture > 14.5 else 0.0
        t_penalty = max(0.0, ((payload.temperature - 35.0) / 7.0) * 100) if payload.temperature > 35.0 else 0.0
        ghi_score = max(0, min(100, round(100.0 - ((0.6 * m_penalty) + (0.4 * t_penalty)))))

        # 4. Value dry matter economic structural shrinkage metrics
        weight_loss = 0.0
        if payload.moisture > 13.5:
            weight_loss = 12000 * ((payload.moisture - 13.5) / 100.0) * (1.35 if clp_f else 1.0)
        
        loss_inr = round(weight_loss * float(profile['base_msp_per_kg']), 2)

        advisories = []
        if clp_m: advisories.append("CRITICAL MOISTURE CEILING EXCEEDED: Run forced ventilation lines immediately.")
        if clp_f: advisories.append("HIGH DANGEROUS MICRO-ORGANIC PATH VECTOR: Extract core warehouse samples.")
        if not advisories: advisories.append("All monitoring data values match nominal target boundaries.")

        # 5. Persist logs to Supabase ledger repository
        insert_sql = """
            INSERT INTO grain_records 
            (ghi_score, fungal_risk_status, biological_activity_index, projected_weight_loss_kg, projected_financial_loss_inr, clp_moisture_violation, clp_temp_violation, clp_humidity_violation, clp_duration_violation, clp_fungal_violation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING record_id;
        """
        cursor.execute(insert_sql, (
            ghi_score, fungal_risk, round(bai, 2), round(weight_loss, 1), loss_inr,
            clp_m, clp_t, clp_h, clp_d, clp_f
        ))
        record_uuid = str(cursor.fetchone()['record_id'])
        conn.commit()

        return AnalysisResponse(
            record_id=record_uuid,
            grain_health_index=ghi_score,
            fungal_risk_status=fungal_risk,
            biological_activity_index=round(bai, 2),
            projected_weight_loss_kg=round(weight_loss, 1),
            estimated_financial_loss_inr=loss_inr,
            clp_matrix=ClpEngineStatus(
                clp_moisture_violation=clp_m, clp_temp_violation=clp_t,
                clp_humidity_violation=clp_h, clp_duration_violation=clp_d, clp_fungal_violation=clp_f
            ),
            action_advisory=advisories
        )
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Analytical Pipeline Intercept Crash: {str(e)}")
    finally:
        cursor.close()
        conn.close()
