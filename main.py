import os
   from fastapi import FastAPI
   from fastapi.middleware.cors import CORSMiddleware
   from pydantic import BaseModel

   app = FastAPI(title="GrainGuardian API")

   # Enable CORS so your web frontend can communicate with it
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["*"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )

   class DiagnosticData(BaseModel):
       crop_type: str
       moisture: float
       temperature: float
       humidity: float

   @app.get("/")
   def read_root():
       return {"status": "GrainGuardian Backend Engine is 24/7 Active"}

   @app.post("/api/v1/calculate")
   def calculate_metrics(data: DiagnosticData):
       # Edge calculation engine logic run on backend fallback
       # GHI calculation logic example
       moisture_penalty = max(0.0, (data.moisture - 14.0) * 10)
       ghi = int(max(0, min(100, 100 - moisture_penalty)))
       
       risk = "LOW" if ghi >= 80 else ("MEDIUM" if ghi >= 40 else "HIGH")
       
       return {
           "ghi_score": ghi,
           "fungal_risk": risk,
           "projected_loss_inr": round(moisture_penalty * 25, 2)
       }