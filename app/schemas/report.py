from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class OperationReportBase(BaseModel):
    report_date: str
    station_code: str


class OperationReportResponse(OperationReportBase):
    id: int
    marshalling_efficiency: float
    avg_stay_time: float
    maintenance_completion_rate: float
    total_arrived: int
    total_departed: int
    total_maintenance: int
    total_containers_handled: int
    generated_at: datetime

    class Config:
        from_attributes = True


class ReportExportRequest(BaseModel):
    start_date: str
    end_date: str
    station_code: Optional[str] = None


class NotificationBase(BaseModel):
    title: str
    content: str
    recipient_role: str
    notification_type: str
    priority: str = "normal"


class NotificationCreate(NotificationBase):
    recipient_id: Optional[int] = None
    related_type: Optional[str] = None
    related_id: Optional[int] = None


class NotificationResponse(NotificationBase):
    id: int
    recipient_id: Optional[int] = None
    related_type: Optional[str] = None
    related_id: Optional[int] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True
