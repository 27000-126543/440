from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, List
from app.schemas.marshalling import VehicleResponse


class MaintenanceTeamBase(BaseModel):
    team_name: str
    skill_type: str
    leader: str
    status: str = "active"


class MaintenanceTeamCreate(MaintenanceTeamBase):
    pass


class MaintenanceTeamResponse(MaintenanceTeamBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class MaintenancePlanBase(BaseModel):
    vehicle_id: int
    maintenance_type: str
    reason: str
    priority: int = 3
    scheduled_start: datetime
    deadline: datetime


class MaintenancePlanCreate(MaintenancePlanBase):
    pass


class MaintenancePlanResponse(MaintenancePlanBase):
    id: int
    plan_no: str
    team_id: Optional[int] = None
    team: Optional[MaintenanceTeamResponse] = None
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    is_overdue: bool
    escalation_level: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FaultRecordBase(BaseModel):
    vehicle_id: int
    fault_type: str
    description: str


class FaultRecordCreate(FaultRecordBase):
    pass


class FaultRecordResponse(FaultRecordBase):
    id: int
    reported_at: datetime
    resolved: bool
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MaintenanceRecordBase(BaseModel):
    plan_id: int
    vehicle_id: int
    description: str
    result: str
    operator: str


class MaintenanceRecordCreate(MaintenanceRecordBase):
    pass


class MaintenanceRecordResponse(MaintenanceRecordBase):
    id: int
    recorded_at: datetime

    class Config:
        from_attributes = True
