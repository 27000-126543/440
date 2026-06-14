from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class ContainerBase(BaseModel):
    container_no: str
    container_type: str
    size: str
    destination: str
    weight: float = 0


class ContainerCreate(ContainerBase):
    pass


class ContainerResponse(ContainerBase):
    id: int
    status: str
    slot_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    arrived_at: datetime
    departed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContainerSlotBase(BaseModel):
    slot_code: str
    slot_type: str
    area: str
    row: int
    bay: int
    tier: int
    capacity: int = 1


class ContainerSlotCreate(ContainerSlotBase):
    pass


class ContainerSlotResponse(ContainerSlotBase):
    id: int
    is_occupied: bool
    containers: List[ContainerResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


class ContainerAssignmentRequest(BaseModel):
    container_id: int
    vehicle_id: int
