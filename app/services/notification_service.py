from sqlalchemy.orm import Session
from app.models.models import Notification
from app.schemas.report import NotificationCreate
from datetime import datetime


def create_notification(db: Session, notification_data: NotificationCreate) -> Notification:
    db_notification = Notification(**notification_data.model_dump())
    db.add(db_notification)
    db.commit()
    db.refresh(db_notification)
    return db_notification


def push_status_notification(
    db: Session,
    title: str,
    content: str,
    notification_type: str,
    related_type: str = None,
    related_id: int = None,
    roles: list = None,
    priority: str = "normal",
):
    if not roles:
        roles = ["dispatcher", "shunter", "maintenance"]

    notifications = []
    for role in roles:
        notif_data = NotificationCreate(
            title=title,
            content=content,
            recipient_role=role,
            notification_type=notification_type,
            related_type=related_type,
            related_id=related_id,
            priority=priority,
        )
        notif = create_notification(db, notif_data)
        notifications.append(notif)

    return notifications


def get_notifications_by_role(db: Session, role: str, skip: int = 0, limit: int = 50) -> list:
    return (
        db.query(Notification)
        .filter(Notification.recipient_role == role)
        .order_by(Notification.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def mark_notification_read(db: Session, notification_id: int) -> Notification:
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
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
