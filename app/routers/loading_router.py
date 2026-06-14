from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas.loading import (
    LoadingRecordResponse,
    LoadingRecordCreate,
    RecheckWorkOrderResponse,
    RecheckSubmitRequest,
)
from app.services.loading_service import (
    create_loading_record,
    get_loading_records,
    get_recheck_work_orders,
    submit_recheck,
)

router = APIRouter(prefix="/loading", tags=["装载管理"])


@router.post("/records", response_model=LoadingRecordResponse)
def add_loading_record(loading_data: LoadingRecordCreate, db: Session = Depends(get_db)):
    record = create_loading_record(db, loading_data)
    if not record:
        raise HTTPException(status_code=404, detail="车辆不存在")
    return record


@router.get("/records", response_model=List[LoadingRecordResponse])
def list_loading_records(
    vehicle_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return get_loading_records(db, vehicle_id, status, skip, limit)


@router.get("/recheck-orders", response_model=List[RecheckWorkOrderResponse])
def list_recheck_orders(
    status: Optional[str] = None,
    vehicle_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return get_recheck_work_orders(db, status, vehicle_id, skip, limit)


@router.post("/recheck-orders/{wo_id}/submit", response_model=RecheckWorkOrderResponse)
def submit_recheck_result(wo_id: int, recheck_data: RecheckSubmitRequest, db: Session = Depends(get_db)):
    wo = submit_recheck(db, wo_id, recheck_data)
    if not wo:
        raise HTTPException(status_code=404, detail="复检工单不存在或已处理")
    return wo
