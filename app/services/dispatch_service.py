from sqlalchemy.orm import Session
from datetime import datetime
import uuid
from typing import Optional, List

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
from app.schemas.report import DispatchFlowResponse, DispatchFlowStep
from app.services.notification_service import push_status_notification, push_dispatch_notification


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

    now = datetime.utcnow()
    dispatch.status = "departure_issued"
    dispatch.driver = driver
    dispatch.departure_time = now
    dispatch.departure_issued_at = now

    plan = db.query(MarshallingPlan).filter(MarshallingPlan.id == dispatch.plan_id).first()
    if plan:
        plan.status = "departed"

        entries = db.query(MarshallingEntry).filter(MarshallingEntry.plan_id == plan.id).all()
        for entry in entries:
            vehicle = db.query(Vehicle).filter(Vehicle.id == entry.vehicle_id).first()
            if vehicle:
                vehicle.status = "departed"
                vehicle.departed_at = now

    db.commit()
    db.refresh(dispatch)

    push_dispatch_notification(
        db,
        train_no=dispatch.train_no,
        driver=driver,
        departure_time=dispatch.departure_time,
        dispatch_no=dispatch.dispatch_no,
        dispatch_id=dispatch.id,
    )

    return {"success": True, "dispatch": dispatch, "message": "发车指令已下发"}


def driver_confirm_departure(db: Session, dispatch_id: int, driver_name: str) -> dict:
    dispatch = db.query(TrainDispatch).filter(TrainDispatch.id == dispatch_id).first()
    if not dispatch:
        return {"success": False, "message": "发车记录不存在"}

    if dispatch.status not in ("departure_issued", "driver_confirmed"):
        return {"success": False, "message": "当前状态不允许司机确认，请先下发发车指令"}

    if dispatch.driver and dispatch.driver != driver_name:
        return {"success": False, "message": "司机姓名不匹配"}

    dispatch.driver_confirmed_at = datetime.utcnow()
    dispatch.status = "driver_confirmed"
    db.commit()
    db.refresh(dispatch)

    push_status_notification(
        db,
        title=f"司机已确认发车 - {dispatch.train_no}",
        content=f"司机 {driver_name} 已确认发车指令，列车 {dispatch.train_no} 即将发车。",
        notification_type="dispatch",
        related_type="dispatch",
        related_id=dispatch.id,
        roles=["dispatcher", "shunter"],
        priority="normal",
    )

    return {"success": True, "dispatch": dispatch, "message": "司机已确认"}


def record_actual_departure(db: Session, dispatch_id: int) -> dict:
    dispatch = db.query(TrainDispatch).filter(TrainDispatch.id == dispatch_id).first()
    if not dispatch:
        return {"success": False, "message": "发车记录不存在"}

    if dispatch.status not in ("departure_issued", "driver_confirmed", "departed"):
        return {"success": False, "message": "请先下发发车指令"}

    dispatch.actual_departure_time = datetime.utcnow()
    dispatch.status = "departed"
    db.commit()
    db.refresh(dispatch)

    push_status_notification(
        db,
        title=f"列车已实际发车 - {dispatch.train_no}",
        content=f"列车 {dispatch.train_no}（司机：{dispatch.driver}）已实际发车，发车编号 {dispatch.dispatch_no}。",
        notification_type="dispatch",
        related_type="dispatch",
        related_id=dispatch.id,
        roles=["dispatcher", "shunter", "maintenance"],
        priority="normal",
    )

    return {"success": True, "dispatch": dispatch, "message": "已记录实际发车时间"}


def get_train_dispatches(
    db: Session, status: str = None, train_no: str = None, skip: int = 0, limit: int = 50
) -> list:
    query = db.query(TrainDispatch)
    if status:
        query = query.filter(TrainDispatch.status == status)
    if train_no:
        query = query.filter(TrainDispatch.train_no == train_no)
    return query.order_by(TrainDispatch.created_at.desc()).offset(skip).limit(limit).all()


def get_dispatch_flow(db: Session, dispatch_id: Optional[int] = None, train_no: Optional[str] = None) -> Optional[DispatchFlowResponse]:
    query = db.query(TrainDispatch)
    if dispatch_id:
        query = query.filter(TrainDispatch.id == dispatch_id)
    elif train_no:
        query = query.filter(TrainDispatch.train_no == train_no).order_by(TrainDispatch.created_at.desc())
    else:
        return None

    dispatch = query.first()
    if not dispatch:
        return None

    plan = db.query(MarshallingPlan).filter(MarshallingPlan.id == dispatch.plan_id).first()
    station_code = plan.station_code if plan else None

    flow: List[DispatchFlowStep] = []

    flow.append(DispatchFlowStep(
        step="发车记录创建",
        status="completed" if dispatch.created_at else "pending",
        timestamp=dispatch.created_at,
        remark=f"创建发车编号：{dispatch.dispatch_no}",
    ))

    flow.append(DispatchFlowStep(
        step="车辆顺序校验",
        status="completed" if dispatch.sequence_checked else "pending",
        timestamp=dispatch.updated_at if dispatch.sequence_checked else None,
        remark="按编组计划校验车辆序号连续性",
    ))

    flow.append(DispatchFlowStep(
        step="制动测试",
        status="completed" if dispatch.brake_test_passed else ("failed" if dispatch.status == "brake_failed" else "pending"),
        timestamp=dispatch.updated_at if dispatch.brake_test_passed else None,
        remark="列车制动安全测试",
    ))

    flow.append(DispatchFlowStep(
        step="发车指令下发",
        status="completed" if dispatch.departure_issued_at else "pending",
        timestamp=dispatch.departure_issued_at,
        remark=f"司机：{dispatch.driver}" if dispatch.driver else None,
    ))

    flow.append(DispatchFlowStep(
        step="司机确认接收",
        status="completed" if dispatch.driver_confirmed_at else "pending",
        timestamp=dispatch.driver_confirmed_at,
        remark="司机端收到指令后确认回执",
    ))

    flow.append(DispatchFlowStep(
        step="实际发车",
        status="completed" if dispatch.actual_departure_time else "pending",
        timestamp=dispatch.actual_departure_time,
        remark="列车驶离场站的实际时间",
    ))

    return DispatchFlowResponse(
        dispatch_id=dispatch.id,
        dispatch_no=dispatch.dispatch_no,
        train_no=dispatch.train_no,
        driver=dispatch.driver,
        status=dispatch.status,
        station_code=station_code,
        created_at=dispatch.created_at,
        flow=flow,
    )


def list_dispatch_flows_by_train(db: Session, train_no: str) -> List[DispatchFlowResponse]:
    dispatches = (
        db.query(TrainDispatch)
        .filter(TrainDispatch.train_no == train_no)
        .order_by(TrainDispatch.created_at.desc())
        .all()
    )
    result = []
    for d in dispatches:
        flow = get_dispatch_flow(db, dispatch_id=d.id)
        if flow:
            result.append(flow)
    return result
