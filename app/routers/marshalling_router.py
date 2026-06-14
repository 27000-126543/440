from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas.marshalling import (
    VehicleArrivalRequest,
    VehicleArrivalResponse,
    MarshallingPlanResponse,
    VehicleResponse,
)
from app.services.marshalling_service import (
    handle_vehicle_arrival,
    get_plans,
    get_plan_by_id,
    start_plan,
)

router = APIRouter(prefix="/marshalling", tags=["编组管理"])


@router.post("/arrival", response_model=VehicleArrivalResponse)
def vehicle_arrival(request: VehicleArrivalRequest, db: Session = Depends(get_db)):
    result = handle_vehicle_arrival(db, request)
    return VehicleArrivalResponse(
        success=result["success"],
        plan=result["plan"],
        message=result["message"],
    )


@router.get("/plans", response_model=List[MarshallingPlanResponse])
def list_plans(
    station_code: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    return get_plans(db, station_code, status, skip, limit)


@router.get("/plans/{plan_id}", response_model=MarshallingPlanResponse)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = get_plan_by_id(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="编组计划不存在")
    return plan


@router.post("/plans/{plan_id}/start", response_model=MarshallingPlanResponse)
def start_marshalling_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = start_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="编组计划不存在")
    return plan
