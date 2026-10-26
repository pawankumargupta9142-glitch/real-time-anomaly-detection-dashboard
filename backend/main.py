"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import SessionLocal, init_db
from models import SimulationStatus

from routes import (
    alerts,
    analytics,
    auth,
    dashboard,
    events,
    model_monitoring,
    reports,
    settings as settings_routes,
    simulator as simulator_routes,
    users,
)

from services.anomaly_model import ensure_model
from services.event_simulator import simulator
from services.websocket_manager import manager


# ---------------------------------------------------------
# Settings
# ---------------------------------------------------------

app_settings = get_settings()


# ---------------------------------------------------------
# Application Lifespan
# ---------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs when the FastAPI application starts and stops.
    """

    # Initialize database
    init_db()

    # Make sure anomaly detection model exists
    ensure_model()

    # Clear stale simulator state after backend restart
    db = SessionLocal()

    try:
        status = db.query(SimulationStatus).first()
        if status and status.is_running:
            activity_times = [
                timestamp
                for timestamp in (status.last_event_at, status.started_at, status.updated_at)
                if timestamp is not None
            ]
            last_activity = max(activity_times) if activity_times else None
            stale_after = max(10, (status.interval_ms or 1500) * 4 / 1000)
            if last_activity is None or datetime.utcnow() - last_activity > timedelta(seconds=stale_after):
                status.is_running = False
                status.stopped_at = datetime.utcnow()
                db.commit()

    finally:
        db.close()

    try:
        yield
    finally:
        if simulator.is_running:
            await simulator.stop()


# ---------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------

app = FastAPI(
    title=app_settings.app_name,
    version=app_settings.app_version,
    description="Real-Time Fraud & Anomaly Detection Dashboard API",
    lifespan=lifespan,
)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,

    # Values from .env
    allow_origins=app_settings.cors_origin_list,

    # Allow localhost and 127.0.0.1 on any port
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",

    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# API Routers
# ---------------------------------------------------------

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(events.router)
app.include_router(alerts.router)
app.include_router(simulator_routes.router)
app.include_router(analytics.router)
app.include_router(reports.router)
app.include_router(users.router)
app.include_router(model_monitoring.router)
app.include_router(settings_routes.router)


# ---------------------------------------------------------
# Health Check
# ---------------------------------------------------------

@app.get("/api/health", tags=["default"])
def health():
    """
    Check whether the FastAPI backend is running.
    """

    return {
        "status": "ok",
        "app": app_settings.app_name,
        "version": app_settings.app_version,
    }


# ---------------------------------------------------------
# WebSocket - Real-Time Events
# ---------------------------------------------------------

@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """
    WebSocket endpoint for the real-time event stream.
    """

    await manager.connect(websocket)

    try:

        # Tell frontend that connection is successful
        await websocket.send_json(
            {
                "type": "connected",
                "data": {
                    "message": "Risk Radar live feed connected"
                },
            }
        )

        # Keep connection alive
        while True:

            message = await websocket.receive_text()

            message = message.strip()

            # -------------------------------------------------
            # Simple heartbeat
            # -------------------------------------------------

            if message.lower() == "ping":
                await manager.send_ping(websocket)
                continue

            # -------------------------------------------------
            # JSON heartbeat
            # -------------------------------------------------

            try:
                payload = json.loads(message)

                if payload.get("type") == "ping":
                    await manager.send_ping(websocket)

            except json.JSONDecodeError:

                # If frontend sends something that isn't JSON,
                # respond with a heartbeat.
                await manager.send_ping(websocket)

    except WebSocketDisconnect:

        manager.disconnect(websocket)

    except Exception:

        manager.disconnect(websocket)