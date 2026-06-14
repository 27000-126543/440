from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid

from app.models.models import (
    PushTask,
    ShuntingEngine,
    Vehicle,
    VehiclePosition,
    MarshallingPlan,
    MarshallingEntry,
)
from app.schemas.shunting import (
    PushTaskCreate,
    ShuntingEngineCreate,
    VehiclePositionCreate,
)
from app.services.notification_service import push_status_notification
from app.config import PUSH_TASK_TIMEOUT_MINUTES


def generate_task_no() -> str:
    return f"PT{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}"


def create_shunting_engine(db: Session, engine_data: ShuntingEngineCreate) -> ShuntingEngine:
    db_engine = ShuntingEngine(**engine_data.model_dump())
    db.add(db_engine)
    db.commit()
    db.refresh(db_engine)
    return db_engine


def get_available_engines(db: Session) -> list:
    return db.query(ShuntingEngine).filter(ShuntingEngine.status == "idle").all()


def find_best_engine(db: Session, source_position: str, priority: int) -> ShuntingEngine:
    available_engines = get_available_engines(db)
    if not available_engines:
        return None

    def engine_score(engine):
        pos_match = 1 if engine.current_position == source_position else 0
        skill_score = engine.skill_level * priority
        return pos_match * 10 + skill_score

    sorted_engines = sorted(available_engines, key=engine_score, reverse=True)
    return sorted_engines[0]


def create_push_task(db: Session, task_data: PushTaskCreate) -> PushTask:
    task_no = generate_task_no()

    db_task = PushTask(
        task_no=task_no,
        plan_id=task_data.plan_id,
        vehicle_id=task_data.vehicle_id,
        source_position=task_data.source_position,
        target_position=task_data.target_position,
        priority=task_data.priority,
        status="pending",
        estimated_completion=datetime.utcnow() + timedelta(minutes=PUSH_TASK_TIMEOUT_MINUTES),
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def assign_engine_to_task(db: Session, task_id: int, engine_id: int) -> PushTask:
    task = db.query(PushTask).filter(PushTask.id == task_id).first()
    engine = db.query(ShuntingEngine).filter(ShuntingEngine.id == engine_id).first()

    if task and engine and engine.status == "idle":
        task.engine_id = engine_id
        task.status = "in_progress"
        task.started_at = datetime.utcnow()

        engine.status = "working"
        engine.current_task_id = task_id

        db.commit()
        db.refresh(task)

        push_status_notification(
            db,
            title=f"推送任务已分配 - {task.task_no}",
            content=f"调车机 {engine.engine_no} 已分配到推送任务 {task.task_no}",
            notification_type="shunting",
            related_type="task",
            related_id=task.id,
            roles=["dispatcher", "shunter"],
            priority="normal",
        )

    return task


def auto_assign_push_tasks(db: Session, plan_id: int = None) -> list:
    query = db.query(PushTask).filter(PushTask.status == "pending")
    if plan_id:
        query = query.filter(PushTask.plan_id == plan_id)

    pending_tasks = query.order_by(PushTask.priority.desc(), PushTask.created_at).all()
    assigned_tasks = []

    for task in pending_tasks:
        engine = find_best_engine(db, task.source_position, task.priority)
        if engine:
            assigned_task = assign_engine_to_task(db, task.id, engine.id)
            assigned_tasks.append(assigned_task)

    return assigned_tasks


def generate_push_tasks_from_plan(db: Session, plan_id: int) -> list:
    plan = db.query(MarshallingPlan).filter(MarshallingPlan.id == plan_id).first()
    if not plan:
        return []

    entries = (
        db.query(MarshallingEntry)
        .filter(MarshallingEntry.plan_id == plan_id)
        .order_by(MarshallingEntry.sequence)
        .all()
    )

    created_tasks = []
    for idx, entry in enumerate(entries):
        vehicle = db.query(Vehicle).filter(Vehicle.id == entry.vehicle_id).first()
        if not vehicle:
            continue

        target_pos = f"{plan.station_code}-{entry.track_no}"

        task_data = PushTaskCreate(
            plan_id=plan_id,
            vehicle_id=vehicle.id,
            source_position=vehicle.current_position,
            target_position=target_pos,
            priority=max(1, 10 - idx),
        )

        task = create_push_task(db, task_data)
        created_tasks.append(task)

    if created_tasks:
        auto_assign_push_tasks(db, plan_id)

    return created_tasks


def track_vehicle_position(db: Session, position_data: VehiclePositionCreate) -> VehiclePosition:
    db_position = VehiclePosition(**position_data.model_dump())
    db.add(db_position)

    vehicle = db.query(Vehicle).filter(Vehicle.id == position_data.vehicle_id).first()
    if vehicle:
        old_position = vehicle.current_position
        vehicle.current_position = position_data.position
        vehicle.updated_at = datetime.utcnow()

        if old_position != position_data.position:
            push_status_notification(
                db,
                title=f"车辆位置更新 - {vehicle.vehicle_no}",
                content=f"车辆 {vehicle.vehicle_no} 从 {old_position} 移动到 {position_data.position}",
                notification_type="tracking",
                related_type="vehicle",
                related_id=vehicle.id,
                roles=["dispatcher", "shunter"],
                priority="normal",
            )

    db.commit()
    db.refresh(db_position)
    return db_position


def complete_push_task(db: Session, task_id: int) -> PushTask:
    task = db.query(PushTask).filter(PushTask.id == task_id).first()
    if not task:
        return None

    task.status = "completed"
    task.completed_at = datetime.utcnow()

    if task.engine_id:
        engine = db.query(ShuntingEngine).filter(ShuntingEngine.id == task.engine_id).first()
        if engine:
            engine.status = "idle"
            engine.current_task_id = None
            engine.current_position = task.target_position

    vehicle = db.query(Vehicle).filter(Vehicle.id == task.vehicle_id).first()
    if vehicle:
        vehicle.current_position = task.target_position
        vehicle.updated_at = datetime.utcnow()

        entry = (
            db.query(MarshallingEntry)
            .filter(
                MarshallingEntry.plan_id == task.plan_id,
                MarshallingEntry.vehicle_id == task.vehicle_id,
            )
            .first()
        )
        if entry:
            entry.status = "completed"
            entry.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(task)

    push_status_notification(
        db,
        title=f"推送任务完成 - {task.task_no}",
        content=f"推送任务 {task.task_no} 已完成，车辆已到达 {task.target_position}",
        notification_type="shunting",
        related_type="task",
        related_id=task.id,
        roles=["dispatcher", "shunter"],
        priority="normal",
    )

    auto_assign_push_tasks(db)

    return task


def check_overdue_tasks(db: Session) -> list:
    now = datetime.utcnow()
    overdue_tasks = (
        db.query(PushTask)
        .filter(
            PushTask.status == "in_progress",
            PushTask.estimated_completion < now,
            PushTask.is_overdue == False,
        )
        .all()
    )

    for task in overdue_tasks:
        task.is_overdue = True
        task.escalation_level = 1

        push_status_notification(
            db,
            title=f"推送任务超时 - {task.task_no}",
            content=f"推送任务 {task.task_no} 已超时，请尽快处理",
            notification_type="shunting",
            related_type="task",
            related_id=task.id,
            roles=["dispatcher", "shunter"],
            priority="high",
        )

    db.commit()
    return overdue_tasks


def escalate_overdue_task(db: Session, task_id: int) -> PushTask:
    task = db.query(PushTask).filter(PushTask.id == task_id).first()
    if task and task.is_overdue:
        task.escalation_level += 1
        db.commit()
        db.refresh(task)

        push_status_notification(
            db,
            title=f"任务升级通知 - {task.task_no}",
            content=f"推送任务 {task.task_no} 已升级到等级 {task.escalation_level}，请主管介入",
            notification_type="escalation",
            related_type="task",
            related_id=task.id,
            roles=["dispatcher"],
            priority="urgent",
        )

    return task


def get_push_tasks(db: Session, status: str = None, engine_id: int = None, skip: int = 0, limit: int = 50) -> list:
    query = db.query(PushTask)
    if status:
        query = query.filter(PushTask.status == status)
    if engine_id:
        query = query.filter(PushTask.engine_id == engine_id)
    return query.order_by(PushTask.created_at.desc()).offset(skip).limit(limit).all()


def get_shunting_engines(db: Session, status: str = None) -> list:
    query = db.query(ShuntingEngine)
    if status:
        query = query.filter(ShuntingEngine.status == status)
    return query.all()


def get_vehicle_positions(db: Session, vehicle_id: int, limit: int = 20) -> list:
    return (
        db.query(VehiclePosition)
        .filter(VehiclePosition.vehicle_id == vehicle_id)
        .order_by(VehiclePosition.timestamp.desc())
        .limit(limit)
        .all()
    )
