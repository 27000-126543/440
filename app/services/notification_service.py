import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.models import Notification
from app.schemas.report import NotificationCreate, NotificationSessionItem, NotificationResponse
from datetime import datetime
from app.utils.notification_manager import notification_manager
from typing import List, Optional, Dict, Any


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


def _apply_notification_filters(
    query,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    notification_type: Optional[str] = None,
    delivery_status: Optional[str] = None,
    is_read: Optional[bool] = None,
    recipient_role: Optional[str] = None,
    recipient_name: Optional[str] = None,
):
    if start_date:
        sd = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(Notification.created_at >= sd)
    if end_date:
        ed = datetime.strptime(end_date, "%Y-%m-%d") + __import__("datetime").timedelta(days=1)
        query = query.filter(Notification.created_at < ed)
    if notification_type:
        query = query.filter(Notification.notification_type == notification_type)
    if delivery_status:
        query = query.filter(Notification.delivery_status == delivery_status)
    if is_read is not None:
        query = query.filter(Notification.is_read == is_read)
    if recipient_role:
        query = query.filter(Notification.recipient_role == recipient_role)
    if recipient_name:
        query = query.filter(Notification.recipient_name == recipient_name)
    return query


def get_notifications_by_role(
    db: Session,
    role: str,
    delivery_status: str = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    notification_type: Optional[str] = None,
    is_read: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
) -> list:
    query = db.query(Notification).filter(Notification.recipient_role == role)
    query = _apply_notification_filters(
        query, start_date, end_date, notification_type, delivery_status, is_read, None, None
    )
    return query.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()


def get_notifications_by_driver_name(
    db: Session,
    driver_name: str,
    delivery_status: str = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    notification_type: Optional[str] = None,
    is_read: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
) -> list:
    query = db.query(Notification).filter(
        Notification.recipient_role == "driver",
        Notification.recipient_name == driver_name,
    )
    query = _apply_notification_filters(
        query, start_date, end_date, notification_type, delivery_status, is_read, None, None
    )
    return query.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()


def get_all_notifications(
    db: Session,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    notification_type: Optional[str] = None,
    delivery_status: Optional[str] = None,
    is_read: Optional[bool] = None,
    recipient_role: Optional[str] = None,
    recipient_name: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> list:
    query = db.query(Notification)
    query = _apply_notification_filters(
        query, start_date, end_date, notification_type, delivery_status, is_read, recipient_role, recipient_name
    )
    return query.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()


def get_notification_sessions(
    db: Session,
    role: Optional[str] = None,
    recipient_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    notification_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[NotificationSessionItem]:
    query = db.query(Notification)
    if role:
        query = query.filter(Notification.recipient_role == role)
    if recipient_name:
        query = query.filter(Notification.recipient_name == recipient_name)
    query = _apply_notification_filters(
        query, start_date, end_date, notification_type, None, None, None, None
    )
    all_notifs = query.order_by(Notification.created_at.desc()).all()

    session_map: Dict[str, Dict[str, Any]] = {}
    for n in all_notifs:
        key = f"{n.related_type or 'none'}:{n.related_id or 0}"
        if key not in session_map:
            subject_map = {
                "dispatch": "发车流程",
                "maintenance": "检修流程",
                "marshalling": "编组流程",
                "loading": "装载流程",
                "container": "集装箱流程",
                "report": "运营报表",
                "system": "系统通知",
            }
            subject = subject_map.get(n.related_type or (n.notification_type if n.notification_type else "system"), "业务流程")
            if n.related_id:
                subject = f"{subject} #{n.related_id}"
            session_map[key] = {
                "related_type": n.related_type,
                "related_id": n.related_id,
                "subject": subject,
                "notifications": [],
                "pending_count": 0,
                "delivered_count": 0,
                "read_count": 0,
            }
        session_map[key]["notifications"].append(n)
        if n.delivery_status == "pending":
            session_map[key]["pending_count"] += 1
        elif n.delivery_status == "delivered":
            session_map[key]["delivered_count"] += 1
        elif n.delivery_status == "read":
            session_map[key]["read_count"] += 1

    session_list = list(session_map.values())
    for s in session_list:
        s["notifications"].sort(key=lambda n: n.created_at)
        s["total_count"] = len(s["notifications"])
        s["first_at"] = s["notifications"][0].created_at
        s["latest_at"] = s["notifications"][-1].created_at
        s["latest_title"] = s["notifications"][-1].title
        s["notifications"].sort(key=lambda n: n.created_at, reverse=True)

    session_list.sort(key=lambda s: s["latest_at"], reverse=True)
    paged = session_list[skip: skip + limit]

    result = []
    for s in paged:
        notif_responses = [NotificationResponse.model_validate(n) for n in s["notifications"]]
        result.append(NotificationSessionItem(
            related_type=s["related_type"],
            related_id=s["related_id"],
            subject=s["subject"],
            total_count=s["total_count"],
            pending_count=s["pending_count"],
            delivered_count=s["delivered_count"],
            read_count=s["read_count"],
            first_at=s["first_at"],
            latest_at=s["latest_at"],
            latest_title=s["latest_title"],
            notifications=notif_responses,
        ))
    return result


def export_notifications_csv(
    db: Session,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    notification_type: Optional[str] = None,
    delivery_status: Optional[str] = None,
    is_read: Optional[bool] = None,
    recipient_role: Optional[str] = None,
    recipient_name: Optional[str] = None,
) -> Dict[str, Any]:
    notifs = get_all_notifications(
        db, start_date, end_date, notification_type, delivery_status,
        is_read, recipient_role, recipient_name, skip=0, limit=10000
    )

    rows = [
        "ID,创建时间,角色,接收人姓名,业务类型,关联类型,关联ID,标题,内容,优先级,投递状态,送达时间,已读时间,是否已读"
    ]
    for n in notifs:
        rows.append(
            f"{n.id},{n.created_at},{n.recipient_role},{n.recipient_name or ''},{n.notification_type},"
            f"{n.related_type or ''},{n.related_id or ''},"
            f"\"{n.title.replace('\"','\"\"')}\",\"{n.content[:100].replace('\"','\"\"')}\","
            f"{n.priority},{n.delivery_status},{n.delivered_at or ''},{n.read_at or ''},{n.is_read}"
        )

    csv_content = "\n".join(rows)
    suffix = ""
    if recipient_role:
        suffix += f"_{recipient_role}"
    if recipient_name:
        suffix += f"_{recipient_name}"
    if notification_type:
        suffix += f"_{notification_type}"
    scope = f"{start_date}_to_{end_date}" if start_date and end_date else "all"
    return {
        "success": True,
        "count": len(notifs),
        "format": "csv",
        "content": csv_content,
        "filename": f"notifications{suffix}_{scope}.csv",
    }


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
