import os
import math
import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="GrainGuardian Database-Connected Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Read the connection string from your environment settings
# Supabase provides this string under Project Settings -> Database
DATABASE_URL = os.environ.get("DATABASE_URL")

class TelemetryInput(BaseModel):
    user_id: str          # Valid UUID string from your user table
    crop_type: str        # 'Paddy' or 'Maize'
    moisture: float       
    temperature: float    
    humidity: float       
    stored_mass_kg: float 

@app.post("/api/v1/analyze")
def analyze_and_save_record(data: TelemetryInput):
    # 1. Calculation Formulations
    m_penalty = max(0.0, ((data.moisture - 14.0) / 6.0) * 100) if data.moisture > 14.0 else 0.0
    t_penalty = max(0.0, ((data.temperature - 35.0) / 15.0) * 100) if data.temperature > 35.0 else 0.0
    h_penalty = max(0.0, ((data.humidity - 70.0) / 30.0) * 100) if data.humidity > 70.0 else 0.0

    aggregated_penalty = (0.50 * m_penalty) + (0.30 * t_penalty) + (0.20 * h_penalty)
    ghi_score = max(0, min(100, round(100.0 - aggregated_penalty)))

    bai = ((data.moisture / 14.0) ** 2) * (data.temperature / 30.0)
    fungal_risk = "LOW" if bai < 1.05 else ("MEDIUM" if bai < 1.30 else "HIGH")

    if data.moisture > 14.0:
        weight_loss_kg = data.stored_mass_kg * ((data.moisture - 14.0) / 100.0) * (1.2 if fungal_risk == "HIGH" else 1.0)
    else:
        weight_loss_kg = 0.0
    
    financial_loss_inr = round(weight_loss_kg * 23.00, 2)

    # 2. Database Insertion Operations
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="Database URL environment variable is missing.")

    try:
        # Establish connection to Supabase instance
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        insert_query = """
        INSERT INTO grain_records (user_id, crop_type, moisture_content, temperature_celsius, relative_humidity, ghi_score, fungal_risk_status, projected_financial_loss_inr, is_synced)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE) RETURNING record_id;
        """
        
        cursor.execute(insert_query, (
            data.user_id,
            data.crop_type,
            data.moisture,
            data.temperature,
            data.humidity,
            ghi_score,
            fungal_risk,
            financial_loss_inr
        ))
        
        inserted_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record calculation log: {str(e)}")

    return {
        "record_id": str(inserted_id),
        "grain_health_index": ghi_score,
        "fungal_risk_status": fungal_risk,
        "estimated_financial_loss_inr": financial_loss_inr,
        "saved_to_cloud": True
    }
