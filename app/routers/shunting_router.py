from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas.shunting import (
    PushTaskResponse,
    ShuntingEngineResponse,
    ShuntingEngineCreate,
    VehiclePositionResponse,
    VehiclePositionCreate,
)
from app.services.shunting_service import (
    create_shunting_engine,
    get_shunting_engines,
    get_push_tasks,
    generate_push_tasks_from_plan,
    auto_assign_push_tasks,
    assign_engine_to_task,
    complete_push_task,
    track_vehicle_position,
    get_vehicle_positions,
    check_overdue_tasks,
    escalate_overdue_task,
)

router = APIRouter(prefix="/shunting", tags=["调车管理"])


@router.post("/engines", response_model=ShuntingEngineResponse)
def add_engine(engine_data: ShuntingEngineCreate, db: Session = Depends(get_db)):
    return create_shunting_engine(db, engine_data)


@router.get("/engines", response_model=List[ShuntingEngineResponse])
def list_engines(status: Optional[str] = None, db: Session = Depends(get_db)):
    return get_shunting_engines(db, status)


@router.get("/tasks", response_model=List[PushTaskResponse])
def list_tasks(
    status: Optional[str] = None,
    engine_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return get_push_tasks(db, status, engine_id, skip, limit)


@router.post("/tasks/generate/{plan_id}", response_model=List[PushTaskResponse])
def generate_tasks_from_plan(plan_id: int, db: Session = Depends(get_db)):
    tasks = generate_push_tasks_from_plan(db, plan_id)
    if not tasks:
        raise HTTPException(status_code=404, detail="计划不存在或无车辆")
    return tasks


@router.post("/tasks/auto-assign")
def auto_assign(plan_id: Optional[int] = None, db: Session = Depends(get_db)):
    assigned = auto_assign_push_tasks(db, plan_id)
    return {"assigned_count": len(assigned), "tasks": assigned}


@router.post("/tasks/{task_id}/assign/{engine_id}", response_model=PushTaskResponse)
def assign_task(task_id: int, engine_id: int, db: Session = Depends(get_db)):
    task = assign_engine_to_task(db, task_id, engine_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务或调车机不存在")
    return task


@router.post("/tasks/{task_id}/complete", response_model=PushTaskResponse)
def complete_task(task_id: int, db: Session = Depends(get_db)):
    task = complete_push_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/vehicle-position", response_model=VehiclePositionResponse)
def record_vehicle_position(position_data: VehiclePositionCreate, db: Session = Depends(get_db)):
    return track_vehicle_position(db, position_data)


@router.get("/vehicles/{vehicle_id}/positions", response_model=List[VehiclePositionResponse])
def list_vehicle_positions(vehicle_id: int, limit: int = 20, db: Session = Depends(get_db)):
    return get_vehicle_positions(db, vehicle_id, limit)


@router.post("/tasks/check-overdue")
def check_overdue(db: Session = Depends(get_db)):
    overdue = check_overdue_tasks(db)
    return {"overdue_count": len(overdue), "tasks": overdue}


@router.post("/tasks/{task_id}/escalate", response_model=PushTaskResponse)
def escalate_task(task_id: int, db: Session = Depends(get_db)):
    task = escalate_overdue_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task
