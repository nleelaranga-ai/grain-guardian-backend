import math
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="GrainGuardian Core Analytical Engine")

# Enable CORS for frontend connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TelemetryInput(BaseModel):
    crop_type: str        # 'Paddy', 'Maize', etc.
    moisture: float       # Percentage (e.g., 16.5)
    temperature: float    # Celsius (e.g., 38.0)
    humidity: float       # Percentage (e.g., 75.0)
    stored_mass_kg: float # Total weight of batch (e.g., 1000)

@app.post("/api/v1/analyze")
def analyze_grain_health(data: TelemetryInput):
    # ----------------------------------------------------
    # 1. CRITICAL LOSS POINT (CLP) ENGINE
    # ----------------------------------------------------
    clp_flags = []
    if data.moisture > 16.5:
        clp_flags.append("CLP-1: High Moisture Danger")
    if data.temperature > 42.0:
        clp_flags.append("CLP-2: High Temperature Anomaly")
    if data.humidity > 80.0:
        clp_flags.append("CLP-3: Severe Atmospheric Humidity")

    # ----------------------------------------------------
    # 2. GRAIN HEALTH INDEX (GHI) MATRIX
    # ----------------------------------------------------
    # Penalties apply when metrics cross safe base thresholds
    m_penalty = max(0.0, ((data.moisture - 14.0) / 6.0) * 100) if data.moisture > 14.0 else 0.0
    t_penalty = max(0.0, ((data.temperature - 35.0) / 15.0) * 100) if data.temperature > 35.0 else 0.0
    h_penalty = max(0.0, ((data.humidity - 70.0) / 30.0) * 100) if data.humidity > 70.0 else 0.0

    # Clamp individual penalties to max 100
    m_penalty = min(m_penalty, 100.0)
    t_penalty = min(t_penalty, 100.0)
    h_penalty = min(h_penalty, 100.0)

    # Weighted composite equation
    aggregated_penalty = (0.50 * m_penalty) + (0.30 * t_penalty) + (0.20 * h_penalty)
    ghi_score = max(0, min(100, round(100.0 - aggregated_penalty)))

    # ----------------------------------------------------
    # 3. FUNGAL RISK PREDICTION ENGINE
    # ----------------------------------------------------
    # Biological Activity Index calculation
    bai = ((data.moisture / 14.0) ** 2) * (data.temperature / 30.0)
    if bai < 1.05:
        fungal_risk = "LOW"
    elif bai < 1.30:
        fungal_risk = "MEDIUM"
    else:
        fungal_risk = "HIGH"

    # ----------------------------------------------------
    # 4. ECONOMIC LOSS ENGINE
    # ----------------------------------------------------
    # Target moisture baseline is 14% for safe storage
    if data.moisture > 14.0:
        variance_factor = (data.moisture - 14.0) / 100.0
        risk_multiplier = 1.2 if fungal_risk == "HIGH" else 1.0
        weight_loss_kg = data.stored_mass_kg * variance_factor * risk_multiplier
    else:
        weight_loss_kg = 0.0

    # Using standard Minimum Support Price (MSP) proxy value for calculations (~₹23/kg)
    msp_per_kg = 23.00
    estimated_financial_loss_inr = round(weight_loss_kg * msp_per_kg, 2)

    # ----------------------------------------------------
    # 5. RECOMMENDATION ENGINE LOGIC MATRIX
    # ----------------------------------------------------
    recommendations = []
    if data.moisture > 14.5:
        recommendations.append("Spread grain for sun drying immediately (ధాన్యమును ఎండబెట్టండి).")
    if data.temperature > 39.0:
        recommendations.append("Turn over the storage pile or increase aeration fan speed.")
    if fungal_risk == "HIGH":
        recommendations.append("CRITICAL: Inspect storage bags immediately for musty odor. Sell or consume within 7 days.")
    if len(recommendations) == 0:
        recommendations.append("Storage values are fully stable. Continue routine checks.")

    return {
        "grain_health_index": ghi_score,
        "critical_loss_points": clp_flags,
        "fungal_risk_status": fungal_risk,
        "projected_weight_loss_kg": round(weight_loss_kg, 2),
        "estimated_financial_loss_inr": estimated_financial_loss_inr,
        "action_advisory": recommendations
    }

@app.get("/")
def health_check():
    return {"status": "GrainGuardian Core Mathematical Engine is Active"}
