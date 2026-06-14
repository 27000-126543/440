from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas.container import (
    ContainerResponse,
    ContainerCreate,
    ContainerSlotResponse,
    ContainerSlotCreate,
    ContainerAssignmentRequest,
)
from app.services.container_service import (
    create_container,
    get_containers,
    create_container_slot,
    get_container_slots,
    match_container_to_vehicle,
    optimize_pickup_order,
    depart_container,
)

router = APIRouter(prefix="/containers", tags=["集装箱管理"])


@router.post("/slots", response_model=ContainerSlotResponse)
def add_slot(slot_data: ContainerSlotCreate, db: Session = Depends(get_db)):
    return create_container_slot(db, slot_data)


@router.get("/slots", response_model=List[ContainerSlotResponse])
def list_slots(
    area: Optional[str] = None,
    is_occupied: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    return get_container_slots(db, area, is_occupied)


@router.post("", response_model=ContainerResponse)
def add_container(container_data: ContainerCreate, db: Session = Depends(get_db)):
    return create_container(db, container_data)


@router.get("", response_model=List[ContainerResponse])
def list_containers(
    status: Optional[str] = None,
    destination: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return get_containers(db, status, destination, skip, limit)


@router.get("/optimize-pickup", response_model=List[ContainerResponse])
def optimize_pickup(
    destination: Optional[str] = None,
    container_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return optimize_pickup_order(db, destination, container_type)


@router.post("/match-vehicle")
def match_vehicle(request: ContainerAssignmentRequest, db: Session = Depends(get_db)):
    result = match_container_to_vehicle(db, request.container_id, request.vehicle_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{container_id}/depart", response_model=ContainerResponse)
def depart(container_id: int, db: Session = Depends(get_db)):
    container = depart_container(db, container_id)
    if not container:
        raise HTTPException(status_code=404, detail="集装箱不存在")
    return container
