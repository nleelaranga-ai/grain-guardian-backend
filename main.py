import math
import os
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(
    title="GrainGuardian Intelligent Engine v3",
    description="IEEE-Compliant Multi-Crop Decision Support Systems Engine",
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

# --- DATA TRANSFER OBJECT SCHEMAS ---
class AnalysisRequest(BaseModel):
    lot_id: str = Field(..., description="Target Storage Lot ID UUID string")
    moisture: float = Field(..., ge=5.0, le=40.0, description="Grain Moisture content %")
    temperature: float = Field(..., ge=0.0, le=75.0, description="Grain Core Pile Temp Celsius")
    humidity: float = Field(..., ge=10.0, le=100.0, description="Ambient Ambient Relative Humidity %")

class ClpEngineStatus(BaseModel):
    clp_moisture_violation: bool
    clp_temp_violation: bool
    clp_humidity_violation: bool
    clp_duration_violation: bool
    clp_fungal_violation: bool

class AnalysisResponse(BaseModel):
    record_id: str
    lot_id: str
    grain_health_index: int
    fungal_risk_status: str
    biological_activity_index: float
    projected_weight_loss_kg: float
    estimated_financial_loss_inr: float
    clp_matrix: ClpEngineStatus
    action_advisory: List[str]

# --- UTILITY CONTEXT CONNECTOR ---
def get_db_connection():
    if not DATABASE_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="System Database Context Target Environment Variable Missing."
        )
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Database Connection Intercept Failure: {str(e)}"
        )

# --- CORE API SERVICE ROUTE ---
@app.post("/api/v3/analyze", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
def execute_grain_intelligence_pass(payload: AnalysisRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. FETCH HISTORIC META CONTEXT MAP
        query = """
            SELECT sl.*, cp.* FROM storage_lots sl
            JOIN crop_profiles cp ON sl.profile_id = cp.profile_id
            WHERE sl.lot_id = %s AND sl.is_active = TRUE;
        """
        cursor.execute(query, (payload.lot_id,))
        lot_context = cursor.fetchone()
        
        if not lot_context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Active Target Storage Lot Context Map not identified."
            )

        # Calculate Storage Track Intersections
        days_in_storage = (datetime.now(timezone.utc) - lot_context['storage_start_date']).days
        days_in_storage = max(0, days_in_storage)

        # 2. EVALUATE FIVE-TIER CRITICAL LOSS POINT MATRIX (CLP)
        clp_moisture = payload.moisture > float(lot_context['critical_moisture_threshold'])
        clp_temp = payload.temperature > float(lot_context['critical_temp_threshold'])
        clp_humidity = payload.humidity > float(lot_context['critical_humidity_threshold'])
        clp_duration = days_in_storage > lot_context['max_safe_storage_days']
        
        # Fungal Engine Equation Pass
        bai = float(((payload.moisture / 14.0) ** 2) * (payload.temperature / 30.0))
        fungal_risk = "LOW" if bai < 1.05 else ("MEDIUM" if bai < 1.30 else "HIGH")
        clp_fungal = fungal_risk == "HIGH"

        # 3. COMPUTE GRAIN HEALTH INDEX (GHI) WITH WEIGHTED PENALTIES
        m_warn = float(lot_context['warning_moisture_threshold'])
        m_crit = float(lot_context['critical_moisture_threshold'])
        m_penalty = max(0.0, ((payload.moisture - m_warn) / (m_crit - m_warn)) * 100) if payload.moisture > m_warn else 0.0

        t_warn = float(lot_context['warning_temp_threshold'])
        t_crit = float(lot_context['critical_temp_threshold'])
        t_penalty = max(0.0, ((payload.temperature - t_warn) / (t_crit - t_warn)) * 100) if payload.temperature > t_warn else 0.0

        h_penalty = max(0.0, ((payload.humidity - 65.0) / 35.0) * 100) if payload.humidity > 65.0 else 0.0

        m_penalty, t_penalty, h_penalty = min(m_penalty, 100.0), min(t_penalty, 100.0), min(h_penalty, 100.0)
        
        aggregated_penalty = (0.45 * m_penalty) + (0.35 * t_penalty) + (0.20 * h_penalty)
        if clp_duration:
            aggregated_penalty += 15.0  # Apply age penalty
            
        ghi_score = max(0, min(100, round(100.0 - aggregated_penalty)))

        # 4. CALCULATE PROJECTED MASS LOSS AND FINANCIAL EXPOSURE
        initial_mass = float(lot_context['initial_mass_kg'])
        msp = float(lot_context['base_msp_per_kg'])
        
        if payload.moisture > m_warn:
            variance_ratio = (payload.moisture - m_warn) / 100.0
            risk_multiplier = 1.3 if fungal_risk == "HIGH" else (1.1 if fungal_risk == "MEDIUM" else 1.0)
            weight_loss_kg = initial_mass * variance_ratio * risk_multiplier
        else:
            weight_loss_kg = 0.0

        weight_loss_kg = min(weight_loss_kg, initial_mass)
        financial_loss_inr = round(weight_loss_kg * msp, 2)

        # 5. GENERATE ADVISORY LOGIC MATRIX TEXT
        advisories = []
        if clp_moisture:
            advisories.append("CRITICAL_MOISTURE: Immediate mechanical aeration required. Content exceeds safety standards.")
        if clp_temp:
            advisories.append("THERMAL_SPIKE_DETECTED: Pile heat buildup indicates high bio-activity. Rotate batch immediately.")
        if clp_fungal:
            advisories.append("FUNGAL_OUTBREAK_RISK: Environmental profile matches micro-organic expansion parameters. Extract core samples.")
        if len(advisories) == 0:
            advisories.append("All monitoring parameters match safe standard baselines. Maintain present containment.")

        # 6. WRITE RESULTS TO HISTORIC POSTGRES DATA TABLE
        insert_query = """
            INSERT INTO grain_records 
            (lot_id, moisture_content, temperature_celsius, relative_humidity, ghi_score, fungal_risk_status, biological_activity_index, projected_weight_loss_kg, projected_financial_loss_inr, clp_moisture_violation, clp_temp_violation, clp_humidity_violation, clp_duration_violation, clp_fungal_violation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING record_id, captured_at;
        """
        cursor.execute(insert_query, (
            payload.lot_id, payload.moisture, payload.temperature, payload.humidity,
            ghi_score, fungal_risk, bai, weight_loss_kg, financial_loss_inr,
            clp_moisture, clp_temp, clp_humidity, clp_duration, clp_fungal
        ))
        
        db_result = cursor.fetchone()
        conn.commit()

        return AnalysisResponse(
            record_id=str(db_result['record_id']),
            lot_id=payload.lot_id,
            grain_health_index=ghi_score,
            fungal_risk_status=fungal_risk,
            biological_activity_index=round(bai, 3),
            projected_weight_loss_kg=round(weight_loss_kg, 2),
            estimated_financial_loss_inr=financial_loss_inr,
            clp_matrix=ClpEngineStatus(
                clp_moisture_violation=clp_moisture,
                clp_temp_violation=clp_temp,
                clp_humidity_violation=clp_humidity,
                clp_duration_violation=clp_duration,
                clp_fungal_violation=clp_fungal
            ),
            action_advisory=advisories
        )

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Engine Analytical Compute Failure Pipeline Crash: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()

# --- AUXILIARY CHRONOLOGICAL TIMESERIES STREAM ---
@app.get("/api/v3/lots/{lot_id}/analytics", status_code=status.HTTP_200_OK)
def get_lot_historical_trend_data(lot_id: str, limit: int = 30):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
            SELECT moisture_content, temperature_celsius, relative_humidity, ghi_score, projected_financial_loss_inr, captured_at 
            FROM grain_records 
            WHERE lot_id = %s 
            ORDER BY captured_at ASC 
            LIMIT %s;
        """
        cursor.execute(query, (lot_id, limit))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
