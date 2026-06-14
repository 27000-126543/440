import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

from app.database import engine, SessionLocal
from app.models.models import Base
from app.routers import (
    marshalling_router,
    shunting_router,
    maintenance_router,
    loading_router,
    container_router,
    dispatch_router,
    report_router,
)
from app.services.report_service import generate_daily_report
from app.services.shunting_service import check_overdue_tasks
from app.services.maintenance_service import check_overdue_maintenance
from app.config import REPORT_GENERATION_HOUR

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="铁路货运编组站智能调度系统",
    description="铁路货运编组站智能调度系统后端API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(marshalling_router.router, prefix="/api/v1")
app.include_router(shunting_router.router, prefix="/api/v1")
app.include_router(maintenance_router.router, prefix="/api/v1")
app.include_router(loading_router.router, prefix="/api/v1")
app.include_router(container_router.router, prefix="/api/v1")
app.include_router(dispatch_router.router, prefix="/api/v1")
app.include_router(report_router.router, prefix="/api/v1")


def scheduled_daily_report():
    db = SessionLocal()
    try:
        date_str = datetime.now().strftime("%Y-%m-%d")
        generate_daily_report(db, date_str)
    finally:
        db.close()


def scheduled_check_overdue():
    db = SessionLocal()
    try:
        check_overdue_tasks(db)
        check_overdue_maintenance(db)
    finally:
        db.close()


@app.on_event("startup")
def startup_event():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        scheduled_daily_report,
        "cron",
        hour=REPORT_GENERATION_HOUR,
        minute=0,
        id="daily_report",
    )
    scheduler.add_job(
        scheduled_check_overdue,
        "interval",
        minutes=30,
        id="check_overdue",
    )
    scheduler.start()
    app.state.scheduler = scheduler


@app.on_event("shutdown")
def shutdown_event():
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()


@app.get("/")
def root():
    return {
        "message": "铁路货运编组站智能调度系统 API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
