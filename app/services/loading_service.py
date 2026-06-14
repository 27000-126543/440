from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from app.models.models import (
    LoadingRecord,
    RecheckWorkOrder,
    Vehicle,
)
from app.schemas.loading import (
    LoadingRecordCreate,
    RecheckWorkOrderCreate,
    RecheckSubmitRequest,
)
from app.services.notification_service import push_status_notification


def generate_wo_no() -> str:
    return f"RC{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}"


def check_weight_consistency(declared_weight: float, measured_weight: float, tolerance: float) -> bool:
    if declared_weight == 0:
        return measured_weight == 0
    diff = abs(measured_weight - declared_weight) / declared_weight
    return diff <= tolerance


def check_cargo_consistency(vehicle_cargo: str, record_cargo: str) -> bool:
    if not vehicle_cargo or not record_cargo:
        return True
    return vehicle_cargo.strip().lower() == record_cargo.strip().lower()


def create_loading_record(db: Session, loading_data: LoadingRecordCreate) -> LoadingRecord:
    vehicle = db.query(Vehicle).filter(Vehicle.id == loading_data.vehicle_id).first()
    if not vehicle:
        return None

    is_weight_consistent = check_weight_consistency(
        loading_data.declared_weight,
        loading_data.measured_weight,
        loading_data.weight_tolerance,
    )

    is_cargo_consistent = check_cargo_consistency(vehicle.cargo_name, loading_data.cargo_name)
    is_consistent = is_weight_consistent and is_cargo_consistent

    db_record = LoadingRecord(
        **loading_data.model_dump(),
        is_consistent=is_consistent,
        recheck_required=not is_consistent,
    )

    if not is_consistent:
        vehicle.is_locked = True
        reasons = []
        if not is_weight_consistent:
            weight_diff_pct = abs(loading_data.measured_weight - loading_data.declared_weight) / loading_data.declared_weight * 100 if loading_data.declared_weight else 0
            reasons.append(f"重量偏差{weight_diff_pct:.1f}%")
        if not is_cargo_consistent:
            reasons.append("品名不一致")

        vehicle.lock_reason = "; ".join(reasons)

        wo_no = generate_wo_no()
        recheck_wo = RecheckWorkOrder(
            wo_no=wo_no,
            loading_record_id=0,
            vehicle_id=loading_data.vehicle_id,
            reason="; ".join(reasons),
            status="pending",
        )
        db.add(recheck_wo)
        db.flush()

        db_record.recheck_work_order_no = wo_no
        recheck_wo.loading_record_id = 0

    db.add(db_record)
    db.flush()

    if not is_consistent:
        recheck_wo.loading_record_id = db_record.id

    db.commit()
    db.refresh(db_record)

    if not is_consistent:
        push_status_notification(
            db,
            title=f"装载校验异常 - {vehicle.vehicle_no}",
            content=f"车辆 {vehicle.vehicle_no} 装载校验未通过，已锁定并生成复检工单",
            notification_type="loading",
            related_type="vehicle",
            related_id=vehicle.id,
            roles=["dispatcher"],
            priority="high",
        )
    else:
        push_status_notification(
            db,
            title=f"装载校验通过 - {vehicle.vehicle_no}",
            content=f"车辆 {vehicle.vehicle_no} 装载校验通过",
            notification_type="loading",
            related_type="vehicle",
            related_id=vehicle.id,
            roles=["dispatcher"],
            priority="normal",
        )

    return db_record


def get_recheck_work_orders(db: Session, status: str = None, vehicle_id: int = None, skip: int = 0, limit: int = 50) -> list:
    query = db.query(RecheckWorkOrder)
    if status:
        query = query.filter(RecheckWorkOrder.status == status)
    if vehicle_id:
        query = query.filter(RecheckWorkOrder.vehicle_id == vehicle_id)
    return query.order_by(RecheckWorkOrder.created_at.desc()).offset(skip).limit(limit).all()


def submit_recheck(db: Session, wo_id: int, recheck_data: RecheckSubmitRequest) -> RecheckWorkOrder:
    wo = db.query(RecheckWorkOrder).filter(RecheckWorkOrder.id == wo_id).first()
    if not wo or wo.status != "pending":
        return None

    wo.status = "completed"
    wo.recheck_result = recheck_data.recheck_result
    wo.rechecked_by = recheck_data.rechecked_by
    wo.rechecked_at = datetime.utcnow()

    vehicle = db.query(Vehicle).filter(Vehicle.id == wo.vehicle_id).first()
    loading_record = db.query(LoadingRecord).filter(LoadingRecord.id == wo.loading_record_id).first()

    if recheck_data.passed:
        if vehicle:
            vehicle.is_locked = False
            vehicle.lock_reason = None

        if loading_record:
            loading_record.status = "passed"
            loading_record.is_consistent = True
            loading_record.recheck_required = False

        push_status_notification(
            db,
            title=f"复检通过 - {wo.wo_no}",
            content=f"复检工单 {wo.wo_no} 已通过，车辆已解锁",
            notification_type="loading",
            related_type="work_order",
            related_id=wo.id,
            roles=["dispatcher"],
            priority="normal",
        )
    else:
        if loading_record:
            loading_record.status = "failed"

        push_status_notification(
            db,
            title=f"复检未通过 - {wo.wo_no}",
            content=f"复检工单 {wo.wo_no} 未通过，请进一步处理",
            notification_type="loading",
            related_type="work_order",
            related_id=wo.id,
            roles=["dispatcher"],
            priority="high",
        )

    db.commit()
    db.refresh(wo)
    return wo


def get_loading_records(db: Session, vehicle_id: int = None, status: str = None, skip: int = 0, limit: int = 50) -> list:
    query = db.query(LoadingRecord)
    if vehicle_id:
        query = query.filter(LoadingRecord.vehicle_id == vehicle_id)
    if status:
        query = query.filter(LoadingRecord.status == status)
    return query.order_by(LoadingRecord.created_at.desc()).offset(skip).limit(limit).all()
