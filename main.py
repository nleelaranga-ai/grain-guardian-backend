import math
import os
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="GrainGuardian Intelligent Engine v3",
    description="IEEE-Compliant Multi-Crop Decision Support Systems Engine",
    version="3.0.0"
)

# Robust Cross-Origin Resource Sharing (CORS) setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    user_id: Optional[str] = "00000000-0000-0000-0000-000000000000"
    crop_type: str = "Paddy (Rice)"
    moisture: float = Field(..., ge=5.0, le=40.0)
    temperature: float = Field(..., ge=0.0, le=75.0)
    humidity: float = Field(..., ge=10.0, le=100.0)
    stored_mass_kg: float = 12000.0

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

@app.post("/api/v1/analyze", response_model=AnalysisResponse, status_code=status.HTTP_200_OK)
@app.post("/api/v3/analyze", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
def execute_grain_intelligence_pass(payload: AnalysisRequest):
    try:
        # Determine crop pricing parameters matching baseline profiles
        msp = 23.20
        safe_limit = 13.5
        crit_moisture = 16.0
        warn_moisture = 14.5
        crit_temp = 42.0
        warn_temp = 35.0

        if "wheat" in payload.crop_type.lower():
            msp = 22.75
            safe_limit = 13.0
            crit_moisture = 15.5
            warn_moisture = 14.0
            crit_temp = 40.0
            warn_temp = 33.0
        elif "maize" in payload.crop_type.lower():
            msp = 20.90
            safe_limit = 13.5
            crit_moisture = 15.8
            warn_moisture = 14.2
            crit_temp = 41.0
            warn_temp = 34.0

        # Biological activity curve math calculations
        bai = float(((payload.moisture / safe_limit) ** 2) * (payload.temperature / 28.0))
        fungal_risk = "LOW" if bai < 1.05 else ("MEDIUM" if bai < 1.30 else "HIGH")

        # Evaluate CLP Threshold boundary rules
        clp_m = payload.moisture > crit_moisture
        clp_t = payload.temperature > crit_temp
        clp_h = payload.humidity > 75.0
        clp_d = False
        clp_f = fungal_risk == "HIGH"

        # Compute GHI score weighted penalty matrix
        m_penalty = max(0.0, ((payload.moisture - warn_moisture) / (crit_moisture - warn_moisture)) * 100) if payload.moisture > warn_moisture else 0.0
        t_penalty = max(0.0, ((payload.temperature - warn_temp) / (crit_temp - warn_temp)) * 100) if payload.temperature > warn_temp else 0.0
        
        aggregated_penalty = (0.6 * m_penalty) + (0.4 * t_penalty)
        ghi_score = max(0, min(100, round(100.0 - aggregated_penalty)))

        # Value economic shrinkage
        weight_loss = 0.0
        if payload.moisture > safe_limit:
            gap_ratio = (payload.moisture - safe_limit) / 100.0
            severity_factor = 1.35 if clp_f else 1.0
            weight_loss = payload.stored_mass_kg * gap_ratio * severity_factor

        loss_inr = round(weight_loss * msp, 2)

        # Advisories
        advisories = []
        if clp_m:
            advisories.append("CRITICAL_MOISTURE: Immediate mechanical aeration required. Moisture content exceeds safe storage ceilings.")
        if clp_t:
            advisories.append("THERMAL_SPIKE_DETECTED: Active hotspot detected in bottom layers. Rotate batch immediately.")
        if clp_f:
            advisories.append("FUNGAL_OUTBREAK_RISK: Biological conditions support rapid mold growth. Extract silo core samples.")
        if not advisories:
            advisories.append("All structural parameters are safe. Maintain hermetic storage conditions.")

        # Return response payload
        return AnalysisResponse(
            record_id=f"rec-{int(datetime.now(timezone.utc).timestamp())}",
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mathematical calculation pipeline error: {str(e)}"
        )
