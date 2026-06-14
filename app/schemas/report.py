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


class DailyTrendItem(BaseModel):
    report_date: str
    station_code: str
    total_arrived: int
    total_departed: int
    marshalling_efficiency: float
    avg_stay_time: float
    maintenance_completion_rate: float
    total_maintenance: int
    total_containers_handled: int


class TrendSummary(BaseModel):
    start_date: str
    end_date: str
    station_codes: List[str]
    total_arrived: int
    total_departed: int
    avg_marshalling_efficiency: float
    avg_stay_time: float
    avg_maintenance_completion_rate: float
    total_maintenance: int
    total_containers_handled: int
    daily_trend: List[DailyTrendItem]


class NotificationBase(BaseModel):
    title: str
    content: str
    recipient_role: str
    notification_type: str
    priority: str = "normal"


class NotificationCreate(NotificationBase):
    recipient_id: Optional[int] = None
    recipient_name: Optional[str] = None
    related_type: Optional[str] = None
    related_id: Optional[int] = None


class NotificationResponse(NotificationBase):
    id: int
    recipient_id: Optional[int] = None
    recipient_name: Optional[str] = None
    related_type: Optional[str] = None
    related_id: Optional[int] = None
    is_read: bool
    delivery_status: str
    created_at: datetime
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NotificationAckRequest(BaseModel):
    notification_ids: List[int]
    ack_type: str = "delivered"


class DispatchFlowStep(BaseModel):
    step: str
    status: str
    timestamp: Optional[datetime] = None
    remark: Optional[str] = None


class DispatchFlowResponse(BaseModel):
    dispatch_id: int
    dispatch_no: str
    train_no: str
    driver: Optional[str] = None
    status: str
    station_code: Optional[str] = None
    created_at: datetime
    flow: List[DispatchFlowStep]
