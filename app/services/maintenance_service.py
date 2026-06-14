from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid

from app.models.models import (
    MaintenancePlan,
    MaintenanceTeam,
    MaintenanceRecord,
    FaultRecord,
    Vehicle,
)
from app.schemas.maintenance import (
    MaintenancePlanCreate,
    MaintenanceTeamCreate,
    FaultRecordCreate,
    MaintenanceRecordCreate,
)
from app.services.notification_service import push_status_notification
from app.config import MAINTENANCE_OVERDUE_HOURS


MILEAGE_THRESHOLDS = {
    "A": 5000,
    "B": 10000,
    "C": 20000,
}

MAINTENANCE_TYPES = {
    "routine": "例行检修",
    "mileage": "里程检修",
    "fault": "故障检修",
}

SKILL_TYPE_MAP = {
    "brake": "制动系统",
    "engine": "动力系统",
    "electric": "电气系统",
    "general": "通用检修",
}


def generate_plan_no() -> str:
    return f"MT{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}"


def create_maintenance_team(db: Session, team_data: MaintenanceTeamCreate) -> MaintenanceTeam:
    db_team = MaintenanceTeam(**team_data.model_dump())
    db.add(db_team)
    db.commit()
    db.refresh(db_team)
    return db_team


def get_maintenance_teams(db: Session, skill_type: str = None) -> list:
    query = db.query(MaintenanceTeam).filter(MaintenanceTeam.status == "active")
    if skill_type:
        query = query.filter(MaintenanceTeam.skill_type == skill_type)
    return query.all()


def determine_skill_type(maintenance_type: str, fault_type: str = None) -> str:
    if fault_type:
        if "制动" in fault_type or "刹车" in fault_type or "brake" in fault_type.lower():
            return "brake"
        if "发动机" in fault_type or "动力" in fault_type or "engine" in fault_type.lower():
            return "engine"
        if "电气" in fault_type or "电路" in fault_type or "electric" in fault_type.lower():
            return "electric"
    return "general"


def assign_team_to_plan(db: Session, plan_id: int, skill_type: str = "general") -> MaintenancePlan:
    plan = db.query(MaintenancePlan).filter(MaintenancePlan.id == plan_id).first()
    if not plan:
        return None

    teams = get_maintenance_teams(db, skill_type)

    if not teams:
        teams = get_maintenance_teams(db, "general")

    if not teams:
        return plan

    team_loads = []
    for team in teams:
        active_count = (
            db.query(MaintenancePlan)
            .filter(
                MaintenancePlan.team_id == team.id,
                MaintenancePlan.status.in_(["pending", "in_progress"]),
            )
            .count()
        )
        team_loads.append((team, active_count))

    team_loads.sort(key=lambda x: x[1])
    best_team = team_loads[0][0]

    plan.team_id = best_team.id
    db.commit()
    db.refresh(plan)

    return plan


def create_maintenance_plan(db: Session, plan_data: MaintenancePlanCreate, station_code: str = None) -> MaintenancePlan:
    plan_no = generate_plan_no()

    db_plan = MaintenancePlan(
        plan_no=plan_no,
        **plan_data.model_dump(),
    )
    if station_code:
        db_plan.station_code = station_code
    db.add(db_plan)
    db.flush()

    skill_type = determine_skill_type(plan_data.maintenance_type)
    db_plan = assign_team_to_plan(db, db_plan.id, skill_type)

    db.commit()
    db.refresh(db_plan)

    push_status_notification(
        db,
        title=f"检修计划生成 - {db_plan.plan_no}",
        content=f"车辆 {plan_data.vehicle_id} 的{MAINTENANCE_TYPES.get(plan_data.maintenance_type, '检修')}计划已生成，已分配到班组",
        notification_type="maintenance",
        related_type="plan",
        related_id=db_plan.id,
        roles=["dispatcher", "maintenance"],
        priority="normal",
    )

    return db_plan


def generate_maintenance_from_mileage(db: Session, vehicle_id: int) -> MaintenancePlan:
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        return None

    mileage = vehicle.mileage
    vehicle_type = vehicle.vehicle_type

    threshold = MILEAGE_THRESHOLDS.get(vehicle_type, 10000)

    if mileage < threshold:
        return None

    existing = (
        db.query(MaintenancePlan)
        .filter(
            MaintenancePlan.vehicle_id == vehicle_id,
            MaintenancePlan.maintenance_type == "mileage",
            MaintenancePlan.status.in_(["pending", "in_progress"]),
        )
        .first()
    )
    if existing:
        return None

    scheduled_start = datetime.utcnow()
    deadline = scheduled_start + timedelta(hours=MAINTENANCE_OVERDUE_HOURS)

    plan_data = MaintenancePlanCreate(
        vehicle_id=vehicle_id,
        maintenance_type="mileage",
        reason=f"行驶里程达到 {mileage:.0f} 公里，需进行里程检修",
        priority=3,
        scheduled_start=scheduled_start,
        deadline=deadline,
    )

    return create_maintenance_plan(db, plan_data, vehicle.station_code)


def generate_maintenance_from_fault(db: Session, fault_record: FaultRecord) -> MaintenancePlan:
    vehicle_id = fault_record.vehicle_id
    fault_type = fault_record.fault_type

    existing = (
        db.query(MaintenancePlan)
        .filter(
            MaintenancePlan.vehicle_id == vehicle_id,
            MaintenancePlan.maintenance_type == "fault",
            MaintenancePlan.status.in_(["pending", "in_progress"]),
        )
        .first()
    )
    if existing:
        return existing

    scheduled_start = datetime.utcnow()
    deadline = scheduled_start + timedelta(hours=MAINTENANCE_OVERDUE_HOURS)

    plan_data = MaintenancePlanCreate(
        vehicle_id=vehicle_id,
        maintenance_type="fault",
        reason=f"故障：{fault_type} - {fault_record.description[:100]}",
        priority=5,
        scheduled_start=scheduled_start,
        deadline=deadline,
    )

    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    vehicle_station = vehicle.station_code if vehicle else None

    plan = create_maintenance_plan(db, plan_data, vehicle_station)

    skill_type = determine_skill_type("fault", fault_type)
    if plan and skill_type != "general":
        assign_team_to_plan(db, plan.id, skill_type)
        db.refresh(plan)

    return plan


def create_fault_record(db: Session, fault_data: FaultRecordCreate) -> FaultRecord:
    db_fault = FaultRecord(**fault_data.model_dump())
    db.add(db_fault)
    db.commit()
    db.refresh(db_fault)

    generate_maintenance_from_fault(db, db_fault)

    push_status_notification(
        db,
        title=f"故障记录 - {fault_data.fault_type}",
        content=f"车辆 {fault_data.vehicle_id} 记录新故障：{fault_data.fault_type}",
        notification_type="fault",
        related_type="fault",
        related_id=db_fault.id,
        roles=["dispatcher", "maintenance"],
        priority="high",
    )

    return db_fault


def start_maintenance(db: Session, plan_id: int) -> MaintenancePlan:
    plan = db.query(MaintenancePlan).filter(MaintenancePlan.id == plan_id).first()
    if plan and plan.status == "pending":
        plan.status = "in_progress"
        plan.started_at = datetime.utcnow()
        db.commit()
        db.refresh(plan)

        push_status_notification(
            db,
            title=f"检修开始 - {plan.plan_no}",
            content=f"检修计划 {plan.plan_no} 已开始执行",
            notification_type="maintenance",
            related_type="plan",
            related_id=plan.id,
            roles=["dispatcher", "maintenance"],
            priority="normal",
        )

    return plan


def complete_maintenance(db: Session, plan_id: int, record_data: MaintenanceRecordCreate) -> MaintenancePlan:
    plan = db.query(MaintenancePlan).filter(MaintenancePlan.id == plan_id).first()
    if not plan:
        return None

    plan.status = "completed"
    plan.completed_at = datetime.utcnow()

    db_record = MaintenanceRecord(**record_data.model_dump())
    db.add(db_record)

    vehicle = db.query(Vehicle).filter(Vehicle.id == plan.vehicle_id).first()
    if vehicle:
        vehicle.status = "maintenance_completed"

    db.commit()
    db.refresh(plan)

    push_status_notification(
        db,
        title=f"检修完成 - {plan.plan_no}",
        content=f"检修计划 {plan.plan_no} 已完成，结果：{record_data.result}",
        notification_type="maintenance",
        related_type="plan",
        related_id=plan.id,
        roles=["dispatcher", "maintenance"],
        priority="normal",
    )

    return plan


def check_overdue_maintenance(db: Session) -> list:
    now = datetime.utcnow()
    overdue_plans = (
        db.query(MaintenancePlan)
        .filter(
            MaintenancePlan.status == "in_progress",
            MaintenancePlan.deadline < now,
            MaintenancePlan.is_overdue == False,
        )
        .all()
    )

    for plan in overdue_plans:
        plan.is_overdue = True
        plan.escalation_level = 1

        push_status_notification(
            db,
            title=f"检修计划超期 - {plan.plan_no}",
            content=f"检修计划 {plan.plan_no} 已超期，请尽快完成",
            notification_type="maintenance",
            related_type="plan",
            related_id=plan.id,
            roles=["dispatcher", "maintenance"],
            priority="high",
        )

    db.commit()
    return overdue_plans


def escalate_maintenance(db: Session, plan_id: int) -> MaintenancePlan:
    plan = db.query(MaintenancePlan).filter(MaintenancePlan.id == plan_id).first()
    if plan and plan.is_overdue:
        plan.escalation_level += 1
        db.commit()
        db.refresh(plan)

        push_status_notification(
            db,
            title=f"检修计划升级 - {plan.plan_no}",
            content=f"检修计划 {plan.plan_no} 已升级到等级 {plan.escalation_level}，请主管介入处理",
            notification_type="escalation",
            related_type="plan",
            related_id=plan.id,
            roles=["dispatcher"],
            priority="urgent",
        )

    return plan


def get_maintenance_plans(
    db: Session,
    status: str = None,
    team_id: int = None,
    vehicle_id: int = None,
    skip: int = 0,
    limit: int = 50,
) -> list:
    query = db.query(MaintenancePlan)
    if status:
        query = query.filter(MaintenancePlan.status == status)
    if team_id:
        query = query.filter(MaintenancePlan.team_id == team_id)
    if vehicle_id:
        query = query.filter(MaintenancePlan.vehicle_id == vehicle_id)
    return query.order_by(MaintenancePlan.created_at.desc()).offset(skip).limit(limit).all()


def get_fault_records(db: Session, vehicle_id: int = None, resolved: bool = None, skip: int = 0, limit: int = 50) -> list:
    query = db.query(FaultRecord)
    if vehicle_id:
        query = query.filter(FaultRecord.vehicle_id == vehicle_id)
    if resolved is not None:
        query = query.filter(FaultRecord.resolved == resolved)
    return query.order_by(FaultRecord.reported_at.desc()).offset(skip).limit(limit).all()
