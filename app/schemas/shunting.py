from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.schemas.marshalling import VehicleResponse


class PushTaskBase(BaseModel):
    vehicle_id: int
    source_position: str
    target_position: str
    priority: int = 5


class PushTaskCreate(PushTaskBase):
    plan_id: int


class PushTaskResponse(PushTaskBase):
    id: int
    task_no: str
    plan_id: int
    engine_id: Optional[int] = None
    status: str
    started_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    is_overdue: bool
    escalation_level: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ShuntingEngineBase(BaseModel):
    engine_no: str
    status: str = "idle"
    current_position: str
    skill_level: int = 1


class ShuntingEngineCreate(ShuntingEngineBase):
    pass


class ShuntingEngineResponse(ShuntingEngineBase):
    id: int
    current_task_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VehiclePositionBase(BaseModel):
    vehicle_id: int
    position: str
    source: str


class VehiclePositionCreate(VehiclePositionBase):
    pass


class VehiclePositionResponse(VehiclePositionBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True
