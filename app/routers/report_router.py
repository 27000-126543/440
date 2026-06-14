import json
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas.report import (
    OperationReportResponse,
    ReportExportRequest,
    NotificationResponse,
    TrendSummary,
    NotificationAckRequest,
)
from app.services.report_service import (
    generate_daily_report,
    get_reports,
    export_reports,
    get_trend_summary,
)
from app.services.notification_service import (
    get_notifications_by_role,
    mark_notification_read,
    get_unread_count,
    get_pending_count,
    get_notifications_by_driver_name,
    get_driver_unread_count,
    get_driver_pending_count,
    mark_driver_notifications_read,
    mark_notifications_ack,
)
from app.utils.notification_manager import notification_manager
from app.config import NOTIFICATION_ROLES

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


@router.get("/reports/trend", response_model=TrendSummary)
def report_trend(
    start_date: str,
    end_date: str,
    station_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_trend_summary(db, start_date, end_date, station_code)


@router.post("/reports/export")
def export_report(request: ReportExportRequest, db: Session = Depends(get_db)):
    result = export_reports(db, request)
    headers = {
        "Content-Disposition": f"attachment; filename={result['filename']}",
    }
    return PlainTextResponse(content=result["content"], media_type="text/csv", headers=headers)


@router.get("/notifications", response_model=List[NotificationResponse])
def list_notifications(
    role: str = Query(..., description=f"角色: {', '.join(NOTIFICATION_ROLES)}"),
    delivery_status: Optional[str] = Query(None, description="pending/delivered/read"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    if role not in NOTIFICATION_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {NOTIFICATION_ROLES}")
    return get_notifications_by_role(db, role, delivery_status, skip, limit)


@router.get("/notifications/unread-count")
def unread_count(
    role: str = Query(..., description=f"角色: {', '.join(NOTIFICATION_ROLES)}"),
    db: Session = Depends(get_db),
):
    if role not in NOTIFICATION_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {NOTIFICATION_ROLES}")
    return {
        "role": role,
        "unread_count": get_unread_count(db, role),
        "pending_count": get_pending_count(db, role),
    }


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_read(notification_id: int, db: Session = Depends(get_db)):
    notif = mark_notification_read(db, notification_id)
    if not notif:
        raise HTTPException(status_code=404, detail="通知不存在")
    return notif


@router.post("/notifications/ack")
def batch_ack(request: NotificationAckRequest, db: Session = Depends(get_db)):
    if request.ack_type not in ("delivered", "read"):
        raise HTTPException(status_code=400, detail="ack_type 必须是 delivered 或 read")
    updated = mark_notifications_ack(db, request.notification_ids, request.ack_type)
    return {"success": True, "updated_count": updated, "ack_type": request.ack_type}


@router.get("/drivers/{driver_name}/notifications", response_model=List[NotificationResponse])
def list_driver_notifications(
    driver_name: str,
    delivery_status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return get_notifications_by_driver_name(db, driver_name, delivery_status, skip, limit)


@router.get("/drivers/{driver_name}/notifications/unread-count")
def driver_unread_count(driver_name: str, db: Session = Depends(get_db)):
    return {
        "role": "driver",
        "driver_name": driver_name,
        "unread_count": get_driver_unread_count(db, driver_name),
        "pending_count": get_driver_pending_count(db, driver_name),
    }


@router.post("/drivers/{driver_name}/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_driver_notif_read(driver_name: str, notification_id: int, db: Session = Depends(get_db)):
    notif = mark_driver_notifications_read(db, driver_name, notification_id)
    if not notif:
        raise HTTPException(status_code=404, detail="通知不存在或不属于该司机")
    return notif


@router.post("/drivers/{driver_name}/notifications/ack")
def driver_batch_ack(driver_name: str, request: NotificationAckRequest, db: Session = Depends(get_db)):
    if request.ack_type not in ("delivered", "read"):
        raise HTTPException(status_code=400, detail="ack_type 必须是 delivered 或 read")
    updated = mark_notifications_ack(
        db, request.notification_ids, request.ack_type, role="driver", recipient_name=driver_name
    )
    return {"success": True, "updated_count": updated, "ack_type": request.ack_type}


@router.websocket("/ws/notifications/{role}")
async def websocket_notifications(
    websocket: WebSocket,
    role: str,
    client_id: Optional[str] = "anonymous",
):
    if role not in NOTIFICATION_ROLES:
        await websocket.close(code=1008, reason=f"Invalid role. Must be one of: {NOTIFICATION_ROLES}")
        return

    await notification_manager.connect(role, client_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                ack_type = msg.get("type")
                notification_ids = msg.get("notification_ids", [])
                if ack_type in ("delivered", "read") and notification_ids:
                    from app.database import SessionLocal
                    db = SessionLocal()
                    try:
                        recipient_name = client_id if role == "driver" else None
                        mark_notifications_ack(
                            db, notification_ids, ack_type, role=role, recipient_name=recipient_name
                        )
                    finally:
                        db.close()
            except Exception:
                pass
    except WebSocketDisconnect:
        notification_manager.disconnect(role, client_id)


@router.websocket("/ws/drivers/{driver_name}")
async def websocket_driver_notifications(
    websocket: WebSocket,
    driver_name: str,
):
    await notification_manager.connect("driver", driver_name, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                ack_type = msg.get("type")
                notification_ids = msg.get("notification_ids", [])
                if ack_type in ("delivered", "read") and notification_ids:
                    from app.database import SessionLocal
                    db = SessionLocal()
                    try:
                        mark_notifications_ack(
                            db, notification_ids, ack_type, role="driver", recipient_name=driver_name
                        )
                    finally:
                        db.close()
            except Exception:
                pass
    except WebSocketDisconnect:
        notification_manager.disconnect("driver", driver_name)


@router.get("/ws/status")
async def websocket_status():
    status = {}
    for role in NOTIFICATION_ROLES:
        status[role] = notification_manager.get_connection_count(role)
    return {
        "total_connections": notification_manager.get_connection_count(),
        "by_role": status,
    }
