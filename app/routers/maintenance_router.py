from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas.maintenance import (
    MaintenancePlanResponse,
    MaintenancePlanCreate,
    MaintenanceTeamResponse,
    MaintenanceTeamCreate,
    FaultRecordResponse,
    FaultRecordCreate,
    MaintenanceRecordResponse,
    MaintenanceRecordCreate,
)
from app.services.maintenance_service import (
    create_maintenance_plan,
    get_maintenance_plans,
    create_maintenance_team,
    get_maintenance_teams,
    create_fault_record,
    get_fault_records,
    start_maintenance,
    complete_maintenance,
    check_overdue_maintenance,
    escalate_maintenance,
    generate_maintenance_from_mileage,
)

router = APIRouter(prefix="/maintenance", tags=["检修管理"])


@router.post("/teams", response_model=MaintenanceTeamResponse)
def add_team(team_data: MaintenanceTeamCreate, db: Session = Depends(get_db)):
    return create_maintenance_team(db, team_data)


@router.get("/teams", response_model=List[MaintenanceTeamResponse])
def list_teams(skill_type: Optional[str] = None, db: Session = Depends(get_db)):
    return get_maintenance_teams(db, skill_type)


@router.get("/plans", response_model=List[MaintenancePlanResponse])
def list_plans(
    status: Optional[str] = None,
    team_id: Optional[int] = None,
    vehicle_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return get_maintenance_plans(db, status, team_id, vehicle_id, skip, limit)


@router.post("/plans", response_model=MaintenancePlanResponse)
def add_plan(plan_data: MaintenancePlanCreate, db: Session = Depends(get_db)):
    return create_maintenance_plan(db, plan_data)


@router.post("/plans/{plan_id}/start", response_model=MaintenancePlanResponse)
def start_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = start_maintenance(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="检修计划不存在")
    return plan


@router.post("/plans/{plan_id}/complete", response_model=MaintenancePlanResponse)
def complete_plan(plan_id: int, record_data: MaintenanceRecordCreate, db: Session = Depends(get_db)):
    plan = complete_maintenance(db, plan_id, record_data)
    if not plan:
        raise HTTPException(status_code=404, detail="检修计划不存在")
    return plan


@router.post("/faults", response_model=FaultRecordResponse)
def add_fault(fault_data: FaultRecordCreate, db: Session = Depends(get_db)):
    return create_fault_record(db, fault_data)


@router.get("/faults", response_model=List[FaultRecordResponse])
def list_faults(
    vehicle_id: Optional[int] = None,
    resolved: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return get_fault_records(db, vehicle_id, resolved, skip, limit)


@router.post("/plans/check-overdue")
def check_overdue(db: Session = Depends(get_db)):
    overdue = check_overdue_maintenance(db)
    return {"overdue_count": len(overdue), "plans": overdue}


@router.post("/plans/{plan_id}/escalate", response_model=MaintenancePlanResponse)
def escalate_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = escalate_maintenance(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="检修计划不存在")
    return plan


@router.post("/generate-from-mileage/{vehicle_id}", response_model=Optional[MaintenancePlanResponse])
def generate_from_mileage(vehicle_id: int, db: Session = Depends(get_db)):
    plan = generate_maintenance_from_mileage(db, vehicle_id)
    return plan
