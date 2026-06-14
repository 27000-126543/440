from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.schemas.marshalling import MarshallingPlanResponse


class TrainDispatchBase(BaseModel):
    train_no: str
    plan_id: int
    scheduled_departure: Optional[datetime] = None


class TrainDispatchCreate(TrainDispatchBase):
    pass


class TrainDispatchResponse(TrainDispatchBase):
    id: int
    dispatch_no: str
    sequence_checked: bool
    brake_test_passed: bool
    status: str
    driver: Optional[str] = None
    departure_time: Optional[datetime] = None
    departure_issued_at: Optional[datetime] = None
    driver_confirmed_at: Optional[datetime] = None
    actual_departure_time: Optional[datetime] = None
    plan: Optional[MarshallingPlanResponse] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BrakeTestRequest(BaseModel):
    passed: bool
    operator: str
    test_details: Optional[str] = None


class DriverConfirmRequest(BaseModel):
    driver_name: str
