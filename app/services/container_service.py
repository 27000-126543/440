from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from app.models.models import (
    Container,
    ContainerSlot,
    Vehicle,
)
from app.schemas.container import (
    ContainerCreate,
    ContainerSlotCreate,
)
from app.services.notification_service import push_status_notification


def create_container_slot(db: Session, slot_data: ContainerSlotCreate) -> ContainerSlot:
    db_slot = ContainerSlot(**slot_data.model_dump())
    db.add(db_slot)
    db.commit()
    db.refresh(db_slot)
    return db_slot


def get_available_slots(db: Session, container_type: str = None, area: str = None) -> list:
    query = db.query(ContainerSlot).filter(ContainerSlot.is_occupied == False)
    if container_type:
        query = query.filter(ContainerSlot.slot_type == container_type)
    if area:
        query = query.filter(ContainerSlot.area == area)
    return query.order_by(ContainerSlot.row, ContainerSlot.bay, ContainerSlot.tier).all()


def find_best_slot(db: Session, container_type: str, destination: str) -> ContainerSlot:
    available_slots = get_available_slots(db, container_type)
    if not available_slots:
        available_slots = get_available_slots(db)

    if not available_slots:
        return None

    destination_prefix = destination[:2] if destination else ""

    def slot_score(slot):
        score = 0
        if slot.slot_type == container_type:
            score += 50
        if destination_prefix and destination_prefix in slot.area:
            score += 30
        score += (10 - slot.row) * 2
        score += (10 - slot.bay)
        return score

    sorted_slots = sorted(available_slots, key=slot_score, reverse=True)
    return sorted_slots[0]


def create_container(db: Session, container_data: ContainerCreate) -> Container:
    db_container = Container(**container_data.model_dump())
    db.add(db_container)
    db.flush()

    slot = find_best_slot(db, container_data.container_type, container_data.destination)
    if slot:
        db_container.slot_id = slot.id
        slot.is_occupied = True

    db.commit()
    db.refresh(db_container)

    if slot:
        push_status_notification(
            db,
            title=f"集装箱进场 - {db_container.container_no}",
            content=f"集装箱 {db_container.container_no} 已分配到堆位 {slot.slot_code}",
            notification_type="container",
            related_type="container",
            related_id=db_container.id,
            roles=["dispatcher"],
            priority="normal",
        )

    return db_container


def optimize_pickup_order(db: Session, destination: str = None, container_type: str = None) -> list:
    query = db.query(Container).filter(Container.status == "in_yard")
    if destination:
        query = query.filter(Container.destination == destination)
    if container_type:
        query = query.filter(Container.container_type == container_type)

    containers = query.all()

    containers_with_slot = []
    for c in containers:
        slot = db.query(ContainerSlot).filter(ContainerSlot.id == c.slot_id).first()
        containers_with_slot.append((c, slot))

    def pickup_score(item):
        container, slot = item
        if not slot:
            return 999
        score = slot.row * 100 + slot.bay * 10 + slot.tier
        return score

    sorted_containers = sorted(containers_with_slot, key=pickup_score)
    return [c for c, s in sorted_containers]


def match_container_to_vehicle(db: Session, container_id: int, vehicle_id: int) -> dict:
    container = db.query(Container).filter(Container.id == container_id).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()

    if not container or not vehicle:
        return {"success": False, "message": "集装箱或车辆不存在"}

    if container.status != "in_yard":
        return {"success": False, "message": "集装箱不在堆场"}

    if container.destination != vehicle.destination:
        return {
            "success": False,
            "message": f"目的地不匹配：集装箱{container.destination} vs 车辆{vehicle.destination}",
        }

    container.vehicle_id = vehicle_id
    container.status = "loading"

    if container.slot_id:
        slot = db.query(ContainerSlot).filter(ContainerSlot.id == container.slot_id).first()
        if slot:
            slot.is_occupied = False
        container.slot_id = None

    db.commit()
    db.refresh(container)

    push_status_notification(
        db,
        title=f"集装箱配车 - {container.container_no}",
        content=f"集装箱 {container.container_no} 已匹配到车辆 {vehicle.vehicle_no}",
        notification_type="container",
        related_type="container",
        related_id=container.id,
        roles=["dispatcher", "shunter"],
        priority="normal",
    )

    return {"success": True, "container": container, "vehicle": vehicle}


def depart_container(db: Session, container_id: int) -> Container:
    container = db.query(Container).filter(Container.id == container_id).first()
    if container:
        container.status = "departed"
        container.departed_at = datetime.utcnow()
        db.commit()
        db.refresh(container)
    return container


def get_containers(db: Session, status: str = None, destination: str = None, skip: int = 0, limit: int = 50) -> list:
    query = db.query(Container)
    if status:
        query = query.filter(Container.status == status)
    if destination:
        query = query.filter(Container.destination == destination)
    return query.order_by(Container.created_at.desc()).offset(skip).limit(limit).all()


def get_container_slots(db: Session, area: str = None, is_occupied: bool = None) -> list:
    query = db.query(ContainerSlot)
    if area:
        query = query.filter(ContainerSlot.area == area)
    if is_occupied is not None:
        query = query.filter(ContainerSlot.is_occupied == is_occupied)
    return query.order_by(ContainerSlot.area, ContainerSlot.row, ContainerSlot.bay, ContainerSlot.tier).all()
