from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class LoadingRecordBase(BaseModel):
    vehicle_id: int
    cargo_name: str
    declared_weight: float
    measured_weight: float
    weight_tolerance: float = 0.05
    operator: str


class LoadingRecordCreate(LoadingRecordBase):
    pass


class LoadingRecordResponse(LoadingRecordBase):
    id: int
    status: str
    is_consistent: bool
    recheck_required: bool
    recheck_work_order_no: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RecheckWorkOrderBase(BaseModel):
    loading_record_id: int
    vehicle_id: int
    reason: str


class RecheckWorkOrderCreate(RecheckWorkOrderBase):
    pass


class RecheckWorkOrderResponse(RecheckWorkOrderBase):
    id: int
    wo_no: str
    status: str
    recheck_result: Optional[str] = None
    rechecked_by: Optional[str] = None
    rechecked_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RecheckSubmitRequest(BaseModel):
    recheck_result: str
    rechecked_by: str
    passed: bool
