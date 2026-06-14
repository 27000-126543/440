from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_no = Column(String(50), unique=True, index=True)
    vehicle_type = Column(String(50))
    destination = Column(String(100))
    train_no = Column(String(50))
    mileage = Column(Float, default=0)
    weight = Column(Float, default=0)
    cargo_name = Column(String(100))
    is_locked = Column(Boolean, default=False)
    lock_reason = Column(String(200), nullable=True)
    current_position = Column(String(100))
    station_code = Column(String(50), nullable=True)
    status = Column(String(50), default="arrived")
    arrived_at = Column(DateTime, default=datetime.utcnow)
    departed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    marshalling_entries = relationship("MarshallingEntry", back_populates="vehicle")
    maintenance_records = relationship("MaintenanceRecord", back_populates="vehicle")
    fault_records = relationship("FaultRecord", back_populates="vehicle")
    loading_records = relationship("LoadingRecord", back_populates="vehicle")


class MarshallingPlan(Base):
    __tablename__ = "marshalling_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_no = Column(String(50), unique=True, index=True)
    plan_type = Column(String(20))
    train_no = Column(String(50))
    destination = Column(String(100))
    status = Column(String(50), default="pending")
    station_code = Column(String(50))
    capacity_checked = Column(Boolean, default=False)
    has_conflict = Column(Boolean, default=False)
    conflict_description = Column(Text, nullable=True)
    suggested_adjustment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    entries = relationship("MarshallingEntry", back_populates="plan")
    push_tasks = relationship("PushTask", back_populates="plan")


class MarshallingEntry(Base):
    __tablename__ = "marshalling_entries"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("marshalling_plans.id"))
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    sequence = Column(Integer)
    track_no = Column(String(20))
    status = Column(String(50), default="pending")
    operation_type = Column(String(20))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    plan = relationship("MarshallingPlan", back_populates="entries")
    vehicle = relationship("Vehicle", back_populates="marshalling_entries")


class ShuntingEngine(Base):
    __tablename__ = "shunting_engines"

    id = Column(Integer, primary_key=True, index=True)
    engine_no = Column(String(50), unique=True, index=True)
    status = Column(String(50), default="idle")
    current_position = Column(String(100))
    current_task_id = Column(Integer, ForeignKey("push_tasks.id"), nullable=True)
    skill_level = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    push_tasks = relationship("PushTask", back_populates="engine", foreign_keys="PushTask.engine_id")


class PushTask(Base):
    __tablename__ = "push_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_no = Column(String(50), unique=True, index=True)
    plan_id = Column(Integer, ForeignKey("marshalling_plans.id"))
    engine_id = Column(Integer, ForeignKey("shunting_engines.id"), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    source_position = Column(String(100))
    target_position = Column(String(100))
    status = Column(String(50), default="pending")
    priority = Column(Integer, default=5)
    started_at = Column(DateTime, nullable=True)
    estimated_completion = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    is_overdue = Column(Boolean, default=False)
    escalation_level = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plan = relationship("MarshallingPlan", back_populates="push_tasks")
    engine = relationship("ShuntingEngine", back_populates="push_tasks", foreign_keys=[engine_id])
    vehicle = relationship("Vehicle")


class VehiclePosition(Base):
    __tablename__ = "vehicle_positions"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    position = Column(String(100))
    timestamp = Column(DateTime, default=datetime.utcnow)
    source = Column(String(50))

    vehicle = relationship("Vehicle")


class MaintenancePlan(Base):
    __tablename__ = "maintenance_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_no = Column(String(50), unique=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    maintenance_type = Column(String(50))
    reason = Column(String(200))
    team_id = Column(Integer, ForeignKey("maintenance_teams.id"), nullable=True)
    station_code = Column(String(50), nullable=True)
    priority = Column(Integer, default=3)
    status = Column(String(50), default="pending")
    scheduled_start = Column(DateTime)
    deadline = Column(DateTime)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    is_overdue = Column(Boolean, default=False)
    escalation_level = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    vehicle = relationship("Vehicle")
    team = relationship("MaintenanceTeam", back_populates="plans")
    records = relationship("MaintenanceRecord", back_populates="plan")


class MaintenanceTeam(Base):
    __tablename__ = "maintenance_teams"

    id = Column(Integer, primary_key=True, index=True)
    team_name = Column(String(100), unique=True)
    skill_type = Column(String(50))
    leader = Column(String(50))
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    plans = relationship("MaintenancePlan", back_populates="team")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("maintenance_plans.id"))
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    description = Column(Text)
    result = Column(String(200))
    operator = Column(String(50))
    recorded_at = Column(DateTime, default=datetime.utcnow)

    plan = relationship("MaintenancePlan", back_populates="records")
    vehicle = relationship("Vehicle", back_populates="maintenance_records")


class FaultRecord(Base):
    __tablename__ = "fault_records"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    fault_type = Column(String(50))
    description = Column(Text)
    reported_at = Column(DateTime, default=datetime.utcnow)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)

    vehicle = relationship("Vehicle", back_populates="fault_records")


class LoadingRecord(Base):
    __tablename__ = "loading_records"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    cargo_name = Column(String(100))
    declared_weight = Column(Float)
    measured_weight = Column(Float)
    weight_tolerance = Column(Float, default=0.05)
    status = Column(String(50), default="pending")
    is_consistent = Column(Boolean, default=True)
    recheck_required = Column(Boolean, default=False)
    recheck_work_order_no = Column(String(50), nullable=True)
    operator = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    vehicle = relationship("Vehicle", back_populates="loading_records")


class RecheckWorkOrder(Base):
    __tablename__ = "recheck_work_orders"

    id = Column(Integer, primary_key=True, index=True)
    wo_no = Column(String(50), unique=True, index=True)
    loading_record_id = Column(Integer, ForeignKey("loading_records.id"))
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    reason = Column(String(200))
    status = Column(String(50), default="pending")
    recheck_result = Column(String(200), nullable=True)
    rechecked_by = Column(String(50), nullable=True)
    rechecked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Container(Base):
    __tablename__ = "containers"

    id = Column(Integer, primary_key=True, index=True)
    container_no = Column(String(50), unique=True, index=True)
    container_type = Column(String(50))
    size = Column(String(20))
    destination = Column(String(100))
    weight = Column(Float, default=0)
    status = Column(String(50), default="in_yard")
    slot_id = Column(Integer, ForeignKey("container_slots.id"), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    station_code = Column(String(50), nullable=True)
    arrived_at = Column(DateTime, default=datetime.utcnow)
    departed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    slot = relationship("ContainerSlot", back_populates="containers")
    vehicle = relationship("Vehicle")


class ContainerSlot(Base):
    __tablename__ = "container_slots"

    id = Column(Integer, primary_key=True, index=True)
    slot_code = Column(String(50), unique=True, index=True)
    slot_type = Column(String(50))
    area = Column(String(50))
    row = Column(Integer)
    bay = Column(Integer)
    tier = Column(Integer)
    is_occupied = Column(Boolean, default=False)
    capacity = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    containers = relationship("Container", back_populates="slot")


class TrainDispatch(Base):
    __tablename__ = "train_dispatches"

    id = Column(Integer, primary_key=True, index=True)
    dispatch_no = Column(String(50), unique=True, index=True)
    train_no = Column(String(50))
    plan_id = Column(Integer, ForeignKey("marshalling_plans.id"))
    sequence_checked = Column(Boolean, default=False)
    brake_test_passed = Column(Boolean, default=False)
    status = Column(String(50), default="pending")
    driver = Column(String(50), nullable=True)
    departure_time = Column(DateTime, nullable=True)
    scheduled_departure = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plan = relationship("MarshallingPlan")


class OperationReport(Base):
    __tablename__ = "operation_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_date = Column(String(20), index=True)
    station_code = Column(String(50), index=True)
    marshalling_efficiency = Column(Float, default=0)
    avg_stay_time = Column(Float, default=0)
    maintenance_completion_rate = Column(Float, default=0)
    total_arrived = Column(Integer, default=0)
    total_departed = Column(Integer, default=0)
    total_maintenance = Column(Integer, default=0)
    total_containers_handled = Column(Integer, default=0)
    generated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = ()


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))
    content = Column(Text)
    recipient_role = Column(String(50))
    recipient_id = Column(Integer, nullable=True)
    recipient_name = Column(String(100), nullable=True)
    notification_type = Column(String(50))
    related_type = Column(String(50), nullable=True)
    related_id = Column(Integer, nullable=True)
    is_read = Column(Boolean, default=False)
    priority = Column(String(20), default="normal")
    created_at = Column(DateTime, default=datetime.utcnow)


class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True, index=True)
    station_code = Column(String(50), unique=True, index=True)
    station_name = Column(String(100))
    capacity = Column(Integer, default=200)
    current_load = Column(Integer, default=0)
    tracks_count = Column(Integer, default=10)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
