from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
import uuid

from app.models.models import (
    Vehicle,
    MarshallingPlan,
    MarshallingEntry,
    Station,
)
from app.schemas.marshalling import (
    VehicleCreate,
    VehicleArrivalRequest,
    MarshallingPlanCreate,
)
from app.services.notification_service import push_status_notification
from app.config import STATION_CAPACITY_DEFAULT


def generate_plan_no() -> str:
    return f"MP{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}"


def generate_track_no(index: int, plan_type: str) -> str:
    prefix = "D" if plan_type == "disassembly" else "J"
    return f"{prefix}{(index % 10) + 1:02d}"


def determine_plan_type(vehicles_data: list) -> str:
    destinations = set(v.destination for v in vehicles_data)
    train_nos = set(v.train_no for v in vehicles_data)

    if len(destinations) > 2 or len(train_nos) > 1:
        return "disassembly"
    return "assembly"


def sort_vehicles_for_plan(vehicles_data: list, plan_type: str) -> list:
    if plan_type == "disassembly":
        return sorted(vehicles_data, key=lambda v: (v.destination, v.vehicle_type))
    else:
        return sorted(vehicles_data, key=lambda v: v.vehicle_type)


def check_station_capacity(db: Session, station_code: str, new_count: int) -> dict:
    station = db.query(Station).filter(Station.station_code == station_code).first()

    if not station:
        station = Station(
            station_code=station_code,
            station_name=station_code,
            capacity=STATION_CAPACITY_DEFAULT,
            current_load=0,
        )
        db.add(station)
        db.commit()
        db.refresh(station)

    current_vehicles = (
        db.query(Vehicle)
        .filter(
            Vehicle.current_position.like(f"%{station_code}%"),
            Vehicle.status != "departed",
        )
        .count()
    )

    after_load = current_vehicles + new_count
    has_capacity_issue = after_load > station.capacity
    available_capacity = station.capacity - current_vehicles

    return {
        "has_capacity_issue": has_capacity_issue,
        "current_load": current_vehicles,
        "capacity": station.capacity,
        "available_capacity": available_capacity,
        "new_count": new_count,
        "after_load": after_load,
    }


def detect_conflicts(db: Session, plan_type: str, train_no: str, station_code: str) -> dict:
    conflicts = []

    existing_plans = (
        db.query(MarshallingPlan)
        .filter(
            MarshallingPlan.station_code == station_code,
            MarshallingPlan.status.in_(["pending", "in_progress"]),
        )
        .all()
    )

    for plan in existing_plans:
        if plan.train_no == train_no and plan.plan_type == plan_type:
            conflicts.append({
                "type": "duplicate_train",
                "plan_id": plan.id,
                "plan_no": plan.plan_no,
                "description": f"同车次 {train_no} 已有进行中的{plan_type}计划",
            })

    if len(conflicts) > 0:
        return {
            "has_conflict": True,
            "conflicts": conflicts,
            "suggested_adjustment": f"建议调整车次 {train_no} 的作业次序，或合并现有计划。可优先处理优先级更高的计划。",
        }

    return {"has_conflict": False, "conflicts": [], "suggested_adjustment": None}


def create_vehicles_from_arrival(db: Session, vehicles_data: list, station_code: str = None) -> list:
    created_vehicles = []
    for v_data in vehicles_data:
        vehicle = Vehicle(**v_data.model_dump())
        vehicle.status = "arrived"
        vehicle.arrived_at = datetime.utcnow()
        if station_code:
            vehicle.station_code = station_code
        db.add(vehicle)
        db.flush()
        created_vehicles.append(vehicle)
    db.commit()
    for v in created_vehicles:
        db.refresh(v)
    return created_vehicles


def create_marshalling_plan(
    db: Session,
    plan_data: MarshallingPlanCreate,
    vehicles: list,
) -> MarshallingPlan:
    plan_no = generate_plan_no()

    db_plan = MarshallingPlan(
        plan_no=plan_no,
        plan_type=plan_data.plan_type,
        train_no=plan_data.train_no,
        destination=plan_data.destination,
        station_code=plan_data.station_code,
        status="pending",
    )
    db.add(db_plan)
    db.flush()

    sorted_vehicles = sorted(vehicles, key=lambda v: vehicles.index(v))

    for idx, vehicle in enumerate(sorted_vehicles):
        track_no = generate_track_no(idx, plan_data.plan_type)
        entry = MarshallingEntry(
            plan_id=db_plan.id,
            vehicle_id=vehicle.id,
            sequence=idx + 1,
            track_no=track_no,
            status="pending",
            operation_type=plan_data.plan_type,
        )
        db.add(entry)

    db.commit()
    db.refresh(db_plan)
    return db_plan


def handle_vehicle_arrival(db: Session, request: VehicleArrivalRequest) -> dict:
    vehicles_data = request.vehicles
    station_code = request.station_code

    plan_type = determine_plan_type(vehicles_data)

    sorted_vehicles_data = sort_vehicles_for_plan(vehicles_data, plan_type)

    capacity_result = check_station_capacity(db, station_code, len(sorted_vehicles_data))

    conflict_result = detect_conflicts(db, plan_type, request.train_no, station_code)

    created_vehicles = create_vehicles_from_arrival(db, sorted_vehicles_data, station_code)

    destination = sorted_vehicles_data[0].destination if sorted_vehicles_data else ""

    plan_data = MarshallingPlanCreate(
        plan_type=plan_type,
        train_no=request.train_no,
        destination=destination,
        station_code=station_code,
        vehicle_ids=[v.id for v in created_vehicles],
    )

    plan = create_marshalling_plan(db, plan_data, created_vehicles)

    plan.capacity_checked = True
    if capacity_result["has_capacity_issue"]:
        plan.has_conflict = True
        plan.conflict_description = f"场站容量不足：当前{capacity_result['current_load']}辆，新增{capacity_result['new_count']}辆，超过容量{capacity_result['capacity']}"
        plan.suggested_adjustment = f"建议分流{capacity_result['after_load'] - capacity_result['capacity']}辆车至其他场站，或优先发车释放容量"
    elif conflict_result["has_conflict"]:
        plan.has_conflict = True
        plan.conflict_description = "; ".join([c["description"] for c in conflict_result["conflicts"]])
        plan.suggested_adjustment = conflict_result["suggested_adjustment"]
    else:
        plan.has_conflict = False
        plan.status = "pending"

    db.commit()
    db.refresh(plan)

    push_status_notification(
        db,
        title=f"车辆到达 - {request.train_no}",
        content=f"{len(created_vehicles)}辆车到达{station_code}站，已生成{plan_type}方案 {plan.plan_no}",
        notification_type="marshalling",
        related_type="plan",
        related_id=plan.id,
        roles=["dispatcher", "shunter"],
        priority="high" if plan.has_conflict else "normal",
    )

    return {
        "success": True,
        "plan": plan,
        "capacity_result": capacity_result,
        "conflict_result": conflict_result,
        "message": f"已生成{plan_type}方案，共{len(created_vehicles)}辆车",
    }


def get_plans(db: Session, station_code: str = None, status: str = None, skip: int = 0, limit: int = 20) -> list:
    query = db.query(MarshallingPlan)
    if station_code:
        query = query.filter(MarshallingPlan.station_code == station_code)
    if status:
        query = query.filter(MarshallingPlan.status == status)
    return query.order_by(MarshallingPlan.created_at.desc()).offset(skip).limit(limit).all()


def get_plan_by_id(db: Session, plan_id: int) -> MarshallingPlan:
    return db.query(MarshallingPlan).filter(MarshallingPlan.id == plan_id).first()


def start_plan(db: Session, plan_id: int) -> MarshallingPlan:
    plan = get_plan_by_id(db, plan_id)
    if plan:
        plan.status = "in_progress"
        db.commit()
        db.refresh(plan)

        push_status_notification(
            db,
            title=f"编组计划开始执行 - {plan.plan_no}",
            content=f"计划 {plan.plan_no} 已开始执行",
            notification_type="marshalling",
            related_type="plan",
            related_id=plan.id,
            roles=["dispatcher", "shunter"],
            priority="high",
        )
    return plan
