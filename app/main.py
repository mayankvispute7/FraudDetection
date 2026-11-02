# app/main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.api.routes import router
from app.models.database import engine, Base
from app.logging_config import configure_logging
from app.limiter import limiter

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SentinelX Real-Time Fraud Engine", version="1.0")

# Apply Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Universal CORS: Supports local file://, localhost:5000, localhost:5500, and cloud deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=False, 
    allow_methods=["*"], 
    allow_headers=["*"],
    expose_headers=["*"],
)

# Initialize JSON Logs
configure_logging()

# Mount API endpoints (/predict, /predict/batch, /metrics, /drift-metrics)
app.include_router(router)

@app.get("/health")
async def health_check():
    return {"status": "online", "message": "SentinelX Enterprise API is online."}

# Serve Frontend Static Assets if available (for 1-click cloud deployment on Render/Railway/Docker)
if os.path.isdir("frontend"):
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join("frontend", "index.html"))

    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        return {"status": "online", "message": "SentinelX Enterprise API is online."}
