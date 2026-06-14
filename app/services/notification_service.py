import asyncio
from sqlalchemy.orm import Session
from app.models.models import Notification
from app.schemas.report import NotificationCreate
from datetime import datetime
from app.utils.notification_manager import notification_manager
from typing import List, Optional


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
        "delivery_status": notif.delivery_status,
        "priority": notif.priority,
        "created_at": notif.created_at.isoformat() if notif.created_at else None,
        "delivered_at": notif.delivered_at.isoformat() if notif.delivered_at else None,
        "read_at": notif.read_at.isoformat() if notif.read_at else None,
    }


async def _broadcast_to_websocket(notification: Notification, db_session_maker=None):
    try:
        message = _serialize_notification(notification)
        delivered = False
        if notification.recipient_role == "driver" and notification.recipient_name:
            delivered = await notification_manager.send_to_recipient(
                "driver", notification.recipient_name, message
            )
        else:
            delivered = await notification_manager.send_to_role(notification.recipient_role, message)
    except Exception:
        delivered = False


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
        is_direct = role == "driver" and name
        delivery = "delivered" if notification_manager.is_connected(role, recipient_name=name) else "pending"

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
        if delivery == "delivered":
            notif.delivery_status = "delivered"
            notif.delivered_at = datetime.utcnow()
            db.commit()
            db.refresh(notif)
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
    db: Session, role: str, delivery_status: str = None, skip: int = 0, limit: int = 50
) -> list:
    query = db.query(Notification).filter(Notification.recipient_role == role)
    if delivery_status:
        query = query.filter(Notification.delivery_status == delivery_status)
    return query.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()


def get_notifications_by_driver_name(
    db: Session, driver_name: str, delivery_status: str = None, skip: int = 0, limit: int = 50
) -> list:
    query = db.query(Notification).filter(
        Notification.recipient_role == "driver",
        Notification.recipient_name == driver_name,
    )
    if delivery_status:
        query = query.filter(Notification.delivery_status == delivery_status)
    return query.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()


def mark_notification_read(db: Session, notification_id: int) -> Optional[Notification]:
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if notif:
        notif.is_read = True
        notif.delivery_status = "read"
        notif.read_at = datetime.utcnow()
        if not notif.delivered_at:
            notif.delivered_at = datetime.utcnow()
        db.commit()
        db.refresh(notif)
    return notif


def mark_notifications_ack(
    db: Session,
    notification_ids: List[int],
    ack_type: str,
    role: str = None,
    recipient_name: str = None,
) -> int:
    query = db.query(Notification).filter(Notification.id.in_(notification_ids))
    if role:
        query = query.filter(Notification.recipient_role == role)
    if recipient_name:
        query = query.filter(Notification.recipient_name == recipient_name)

    updated_count = 0
    now = datetime.utcnow()
    for notif in query.all():
        if ack_type == "delivered":
            if notif.delivery_status == "pending":
                notif.delivery_status = "delivered"
                notif.delivered_at = now
                updated_count += 1
        elif ack_type == "read":
            notif.is_read = True
            notif.delivery_status = "read"
            notif.read_at = now
            if not notif.delivered_at:
                notif.delivered_at = now
            updated_count += 1
    if updated_count > 0:
        db.commit()
    return updated_count


def get_unread_count(db: Session, role: str) -> int:
    return db.query(Notification).filter(
        Notification.recipient_role == role, Notification.is_read == False
    ).count()


def get_pending_count(db: Session, role: str) -> int:
    return db.query(Notification).filter(
        Notification.recipient_role == role, Notification.delivery_status == "pending"
    ).count()


def get_driver_unread_count(db: Session, driver_name: str) -> int:
    return db.query(Notification).filter(
        Notification.recipient_role == "driver",
        Notification.recipient_name == driver_name,
        Notification.is_read == False,
    ).count()


def get_driver_pending_count(db: Session, driver_name: str) -> int:
    return db.query(Notification).filter(
        Notification.recipient_role == "driver",
        Notification.recipient_name == driver_name,
        Notification.delivery_status == "pending",
    ).count()


def mark_driver_notifications_read(
    db: Session, driver_name: str, notification_id: int
) -> Optional[Notification]:
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.recipient_role == "driver",
        Notification.recipient_name == driver_name,
    ).first()
    if notif:
        notif.is_read = True
        notif.delivery_status = "read"
        notif.read_at = datetime.utcnow()
        if not notif.delivered_at:
            notif.delivered_at = datetime.utcnow()
        db.commit()
        db.refresh(notif)
    return notif
