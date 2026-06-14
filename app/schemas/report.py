from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Dict


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
    station_codes: Optional[List[str]] = None


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


class DailyTotalTrendItem(BaseModel):
    report_date: str
    total_arrived: int
    total_departed: int
    avg_marshalling_efficiency: float
    avg_stay_time: float
    avg_maintenance_completion_rate: float
    total_maintenance: int
    total_containers_handled: int


class HourlyDistributionItem(BaseModel):
    hour: int
    station_code: str
    arrived_count: int
    departed_count: int


class HourlyDistributionSummary(BaseModel):
    start_date: str
    end_date: str
    station_codes: List[str]
    by_station: List[HourlyDistributionItem]
    total: Dict[str, Dict[str, int]]


class TrainDistributionItem(BaseModel):
    station_code: str
    train_no: str
    total_arrived_vehicles: int
    total_departures: int
    first_arrival: Optional[datetime] = None
    last_departure: Optional[datetime] = None


class TrainDistributionSummary(BaseModel):
    start_date: str
    end_date: str
    station_codes: List[str]
    items: List[TrainDistributionItem]
    total_trains: int
    total_arrived_vehicles: int
    total_departures: int


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
    daily_total_trend: List[DailyTotalTrendItem]


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


class NotificationQueryRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notification_type: Optional[str] = None
    delivery_status: Optional[str] = None
    is_read: Optional[bool] = None
    recipient_role: Optional[str] = None
    recipient_name: Optional[str] = None
    station_codes: Optional[List[str]] = None


class SessionTimelineEvent(BaseModel):
    event_index: int
    title: str
    delivery_status: str
    at: datetime
    notification_id: int
    content: str
    prev_interval_seconds: Optional[float] = None


class NotificationSessionItem(BaseModel):
    related_type: Optional[str]
    related_id: Optional[int]
    subject: str
    total_count: int
    pending_count: int
    delivered_count: int
    read_count: int
    first_at: datetime
    latest_at: datetime
    latest_title: str
    total_duration_seconds: float
    notifications: List[NotificationResponse]
    timeline: List[SessionTimelineEvent]


class DispatchDelayItem(BaseModel):
    dispatch_id: int
    dispatch_no: str
    train_no: str
    driver: Optional[str]
    station_code: Optional[str]
    scheduled_departure: Optional[datetime] = None
    departure_issued_at: Optional[datetime] = None
    driver_confirmed_at: Optional[datetime] = None
    actual_departure_time: Optional[datetime] = None
    issue_delay_seconds: Optional[float] = None
    confirm_delay_seconds: Optional[float] = None
    actual_delay_seconds: Optional[float] = None
    total_delay_seconds: Optional[float] = None


class DriverDelayStats(BaseModel):
    driver: str
    total_dispatches: int
    avg_confirm_delay_seconds: float
    avg_actual_delay_seconds: float
    bottleneck_stage: str


class StationDelayStats(BaseModel):
    station_code: str
    total_dispatches: int
    avg_issue_delay_seconds: float
    avg_confirm_delay_seconds: float
    avg_actual_delay_seconds: float
    bottleneck_stage: str


class DispatchDelaySummary(BaseModel):
    start_date: str
    end_date: str
    station_codes: List[str]
    total_dispatches: int
    dispatches: List[DispatchDelayItem]
    by_driver: List[DriverDelayStats]
    by_station: List[StationDelayStats]


class DispatchVehicleItem(BaseModel):
    vehicle_id: int
    vehicle_no: str
    vehicle_type: str
    destination: str
    arrived_at: Optional[datetime] = None
    departed_at: Optional[datetime] = None
    stay_hours: Optional[float] = None


class DispatchFlowStep(BaseModel):
    step: str
    status: str
    timestamp: Optional[datetime] = None
    remark: Optional[str] = None
    interval_seconds: Optional[float] = None


class DispatchFlowResponse(BaseModel):
    dispatch_id: int
    dispatch_no: str
    train_no: str
    driver: Optional[str] = None
    status: str
    station_code: Optional[str] = None
    created_at: datetime
    flow: List[DispatchFlowStep]
    vehicles: List[DispatchVehicleItem]
    total_elapsed_seconds: Optional[float] = None
