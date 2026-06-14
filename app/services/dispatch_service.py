from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from app.models.models import (
    TrainDispatch,
    MarshallingPlan,
    MarshallingEntry,
    Vehicle,
)
from app.schemas.dispatch import (
    TrainDispatchCreate,
    BrakeTestRequest,
)
from app.services.notification_service import push_status_notification


def generate_dispatch_no() -> str:
    return f"TD{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}"


def check_vehicle_sequence(db: Session, plan_id: int) -> dict:
    entries = (
        db.query(MarshallingEntry)
        .filter(MarshallingEntry.plan_id == plan_id)
        .order_by(MarshallingEntry.sequence)
        .all()
    )

    if not entries:
        return {"passed": False, "message": "没有编组记录", "issues": ["无编组记录"]}

    issues = []
    expected_sequence = 1
    for entry in entries:
        if entry.status != "completed":
            issues.append(f"车辆 {entry.vehicle_id} 状态为 {entry.status}，未完成编组")
        if entry.sequence != expected_sequence:
            issues.append(f"序号不连续：期望{expected_sequence}，实际{entry.sequence}")
        expected_sequence += 1

    return {
        "passed": len(issues) == 0,
        "total_vehicles": len(entries),
        "completed_count": sum(1 for e in entries if e.status == "completed"),
        "issues": issues,
    }


def create_train_dispatch(db: Session, dispatch_data: TrainDispatchCreate) -> TrainDispatch:
    dispatch_no = generate_dispatch_no()

    db_dispatch = TrainDispatch(
        dispatch_no=dispatch_no,
        **dispatch_data.model_dump(),
    )
    db.add(db_dispatch)
    db.commit()
    db.refresh(db_dispatch)

    return db_dispatch


def verify_sequence(db: Session, dispatch_id: int) -> dict:
    dispatch = db.query(TrainDispatch).filter(TrainDispatch.id == dispatch_id).first()
    if not dispatch:
        return {"success": False, "message": "发车记录不存在"}

    result = check_vehicle_sequence(db, dispatch.plan_id)

    dispatch.sequence_checked = True
    if not result["passed"]:
        dispatch.status = "sequence_failed"
    else:
        if dispatch.brake_test_passed:
            dispatch.status = "ready"

    db.commit()
    db.refresh(dispatch)

    return {
        "success": True,
        "passed": result["passed"],
        "details": result,
        "dispatch": dispatch,
    }


def record_brake_test(db: Session, dispatch_id: int, test_data: BrakeTestRequest) -> dict:
    dispatch = db.query(TrainDispatch).filter(TrainDispatch.id == dispatch_id).first()
    if not dispatch:
        return {"success": False, "message": "发车记录不存在"}

    dispatch.brake_test_passed = test_data.passed

    if test_data.passed:
        if dispatch.sequence_checked:
            dispatch.status = "ready"
        else:
            dispatch.status = "brake_passed"
    else:
        dispatch.status = "brake_failed"

    db.commit()
    db.refresh(dispatch)

    if test_data.passed:
        push_status_notification(
            db,
            title=f"制动测试通过 - {dispatch.dispatch_no}",
            content=f"列车 {dispatch.train_no} 制动测试通过",
            notification_type="dispatch",
            related_type="dispatch",
            related_id=dispatch.id,
            roles=["dispatcher"],
            priority="normal",
        )
    else:
        push_status_notification(
            db,
            title=f"制动测试未通过 - {dispatch.dispatch_no}",
            content=f"列车 {dispatch.train_no} 制动测试未通过，请检修",
            notification_type="dispatch",
            related_type="dispatch",
            related_id=dispatch.id,
            roles=["dispatcher", "maintenance"],
            priority="high",
        )

    return {"success": True, "dispatch": dispatch}


def issue_departure_command(db: Session, dispatch_id: int, driver: str) -> dict:
    dispatch = db.query(TrainDispatch).filter(TrainDispatch.id == dispatch_id).first()
    if not dispatch:
        return {"success": False, "message": "发车记录不存在"}

    if not dispatch.sequence_checked:
        return {"success": False, "message": "顺序校验未完成"}

    if not dispatch.brake_test_passed:
        return {"success": False, "message": "制动测试未通过"}

    dispatch.status = "departed"
    dispatch.driver = driver
    dispatch.departure_time = datetime.utcnow()

    plan = db.query(MarshallingPlan).filter(MarshallingPlan.id == dispatch.plan_id).first()
    if plan:
        plan.status = "departed"

        entries = db.query(MarshallingEntry).filter(MarshallingEntry.plan_id == plan.id).all()
        for entry in entries:
            vehicle = db.query(Vehicle).filter(Vehicle.id == entry.vehicle_id).first()
            if vehicle:
                vehicle.status = "departed"
                vehicle.departed_at = datetime.utcnow()

    db.commit()
    db.refresh(dispatch)

    push_status_notification(
        db,
        title=f"发车指令 - {dispatch.train_no}",
        content=f"列车 {dispatch.train_no} 已发车，司机：{driver}，发车时间：{dispatch.departure_time}",
        notification_type="dispatch",
        related_type="dispatch",
        related_id=dispatch.id,
        roles=["dispatcher", "shunter", "maintenance"],
        priority="high",
    )

    return {"success": True, "dispatch": dispatch, "message": "发车指令已下发"}


def get_train_dispatches(db: Session, status: str = None, train_no: str = None, skip: int = 0, limit: int = 50) -> list:
    query = db.query(TrainDispatch)
    if status:
        query = query.filter(TrainDispatch.status == status)
    if train_no:
        query = query.filter(TrainDispatch.train_no == train_no)
    return query.order_by(TrainDispatch.created_at.desc()).offset(skip).limit(limit).all()
