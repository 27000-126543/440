from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas.report import (
    OperationReportResponse,
    ReportExportRequest,
    NotificationResponse,
)
from app.services.report_service import (
    generate_daily_report,
    get_reports,
    export_reports,
)
from app.services.notification_service import (
    get_notifications_by_role,
    mark_notification_read,
    get_unread_count,
)

router = APIRouter(tags=["报表与通知"])


@router.post("/reports/generate", response_model=List[OperationReportResponse])
def generate_report(date: Optional[str] = None, station_code: Optional[str] = None, db: Session = Depends(get_db)):
    return generate_daily_report(db, date, station_code)


@router.get("/reports", response_model=List[OperationReportResponse])
def list_reports(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    station_code: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return get_reports(db, start_date, end_date, station_code, skip, limit)


@router.post("/reports/export")
def export_report(request: ReportExportRequest, db: Session = Depends(get_db)):
    result = export_reports(db, request)
    headers = {
        "Content-Disposition": f"attachment; filename={result['filename']}",
    }
    return PlainTextResponse(content=result["content"], media_type="text/csv", headers=headers)


@router.get("/notifications", response_model=List[NotificationResponse])
def list_notifications(role: str, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return get_notifications_by_role(db, role, skip, limit)


@router.get("/notifications/unread-count")
def unread_count(role: str, db: Session = Depends(get_db)):
    return {"role": role, "unread_count": get_unread_count(db, role)}


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_read(notification_id: int, db: Session = Depends(get_db)):
    notif = mark_notification_read(db, notification_id)
    if not notif:
        raise HTTPException(status_code=404, detail="通知不存在")
    return notif
