from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class VehicleBase(BaseModel):
    vehicle_no: str
    vehicle_type: str
    destination: str
    train_no: str
    mileage: float = 0
    weight: float = 0
    cargo_name: Optional[str] = None
    current_position: str


class VehicleCreate(VehicleBase):
    pass


class VehicleResponse(VehicleBase):
    id: int
    is_locked: bool
    lock_reason: Optional[str] = None
    status: str
    arrived_at: datetime
    departed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MarshallingPlanBase(BaseModel):
    plan_type: str
    train_no: str
    destination: str
    station_code: str


class MarshallingPlanCreate(MarshallingPlanBase):
    vehicle_ids: List[int]


class MarshallingEntryResponse(BaseModel):
    id: int
    plan_id: int
    vehicle_id: int
    vehicle: Optional[VehicleResponse] = None
    sequence: int
    track_no: str
    status: str
    operation_type: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MarshallingPlanResponse(MarshallingPlanBase):
    id: int
    plan_no: str
    status: str
    capacity_checked: bool
    has_conflict: bool
    conflict_description: Optional[str] = None
    suggested_adjustment: Optional[str] = None
    entries: List[MarshallingEntryResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VehicleArrivalRequest(BaseModel):
    vehicles: List[VehicleCreate]
    station_code: str
    train_no: str


class VehicleArrivalResponse(BaseModel):
    success: bool
    plan: Optional[MarshallingPlanResponse] = None
    message: str
