import asyncio
from sqlalchemy.orm import Session
from app.models.models import Notification
from app.schemas.report import NotificationCreate
from datetime import datetime
from app.utils.notification_manager import notification_manager


def create_notification(db: Session, notification_data: NotificationCreate) -> Notification:
    db_notification = Notification(**notification_data.model_dump())
    db.add(db_notification)
    db.commit()
    db.refresh(db_notification)
    return db_notification


def _serialize_notification(notif: Notification) -> dict:
    return {
        "id": notif.id,
        "title": notif.title,
        "content": notif.content,
        "recipient_role": notif.recipient_role,
        "recipient_id": notif.recipient_id,
        "recipient_name": notif.recipient_name,
        "notification_type": notif.notification_type,
        "related_type": notif.related_type,
        "related_id": notif.related_id,
        "is_read": notif.is_read,
        "priority": notif.priority,
        "created_at": notif.created_at.isoformat() if notif.created_at else None,
    }


async def _broadcast_to_websocket(notification: Notification):
    try:
        message = _serialize_notification(notification)
        if notification.recipient_role == "driver" and notification.recipient_name:
            await notification_manager.send_to_recipient(
                "driver", notification.recipient_name, message
            )
        else:
            await notification_manager.send_to_role(notification.recipient_role, message)
    except Exception:
        pass


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        new_loop = asyncio.new_event_loop()
        try:
            new_loop.run_until_complete(coro)
        finally:
            new_loop.close()


def push_status_notification(
    db: Session,
    title: str,
    content: str,
    notification_type: str,
    related_type: str = None,
    related_id: int = None,
    roles: list = None,
    priority: str = "normal",
    recipient_name: str = None,
    recipient_id: int = None,
):
    if not roles:
        roles = ["dispatcher", "shunter", "maintenance"]

    notifications = []
    for role in roles:
        name = recipient_name if role == "driver" else None
        notif_data = NotificationCreate(
            title=title,
            content=content,
            recipient_role=role,
            notification_type=notification_type,
            related_type=related_type,
            related_id=related_id,
            priority=priority,
            recipient_id=recipient_id,
            recipient_name=name,
        )
        notif = create_notification(db, notif_data)
        notifications.append(notif)
        _run_async(_broadcast_to_websocket(notif))

    return notifications


def push_dispatch_notification(
    db: Session,
    train_no: str,
    driver: str,
    departure_time: datetime,
    dispatch_no: str,
    dispatch_id: int,
):
    content = (
        f"【发车指令】车次：{train_no}，司机：{driver}，"
        f"发车时间：{departure_time.strftime('%Y-%m-%d %H:%M:%S')}，"
        f"发车编号：{dispatch_no}，请立即做好发车准备。"
    )

    push_status_notification(
        db,
        title=f"发车指令 - {train_no}",
        content=content,
        notification_type="dispatch",
        related_type="dispatch",
        related_id=dispatch_id,
        roles=["dispatcher", "shunter", "maintenance", "driver"],
        priority="high",
        recipient_name=driver,
    )


def get_notifications_by_role(
    db: Session, role: str, skip: int = 0, limit: int = 50
) -> list:
    return (
        db.query(Notification)
        .filter(Notification.recipient_role == role)
        .order_by(Notification.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_notifications_by_driver_name(
    db: Session, driver_name: str, skip: int = 0, limit: int = 50
) -> list:
    return (
        db.query(Notification)
        .filter(
            Notification.recipient_role == "driver",
            Notification.recipient_name == driver_name,
        )
        .order_by(Notification.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def mark_notification_read(db: Session, notification_id: int) -> Notification:
    notif = (
        db.query(Notification).filter(Notification.id == notification_id).first()
    )
    if notif:
        notif.is_read = True
        db.commit()
        db.refresh(notif)
    return notif


def get_unread_count(db: Session, role: str) -> int:
    return (
        db.query(Notification)
        .filter(Notification.recipient_role == role, Notification.is_read == False)
        .count()
    )


def get_driver_unread_count(db: Session, driver_name: str) -> int:
    return (
        db.query(Notification)
        .filter(
            Notification.recipient_role == "driver",
            Notification.recipient_name == driver_name,
            Notification.is_read == False,
        )
        .count()
    )


def mark_driver_notifications_read(db: Session, driver_name: str, notification_id: int) -> Notification:
    notif = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.recipient_role == "driver",
            Notification.recipient_name == driver_name,
        )
        .first()
    )
    if notif:
        notif.is_read = True
        db.commit()
        db.refresh(notif)
    return notif
