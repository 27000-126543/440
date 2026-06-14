from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from app.models.models import (
    OperationReport,
    Vehicle,
    MarshallingPlan,
    MaintenancePlan,
    Container,
    Station,
)
from app.schemas.report import ReportExportRequest
from app.services.notification_service import push_status_notification


def calculate_marshalling_efficiency(db: Session, date_str: str, station_code: str = None) -> float:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    query = db.query(MarshallingPlan).filter(
        MarshallingPlan.created_at >= date_obj,
        MarshallingPlan.created_at < next_day,
    )
    if station_code:
        query = query.filter(MarshallingPlan.station_code == station_code)

    total_plans = query.count()
    if total_plans == 0:
        return 0.0

    completed_plans = query.filter(MarshallingPlan.status.in_(["completed", "departed"])).count()

    return round(completed_plans / total_plans * 100, 2)


def calculate_avg_stay_time(db: Session, date_str: str, station_code: str = None) -> float:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    query = db.query(Vehicle).filter(
        Vehicle.arrived_at >= date_obj - timedelta(days=7),
        Vehicle.departed_at != None,
        Vehicle.departed_at < next_day,
    )

    vehicles = query.all()
    if not vehicles:
        return 0.0

    total_hours = 0
    for v in vehicles:
        if v.arrived_at and v.departed_at:
            stay_hours = (v.departed_at - v.arrived_at).total_seconds() / 3600
            total_hours += stay_hours

    return round(total_hours / len(vehicles), 2)


def calculate_maintenance_completion_rate(db: Session, date_str: str, station_code: str = None) -> float:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    query = db.query(MaintenancePlan).filter(
        MaintenancePlan.created_at >= date_obj,
        MaintenancePlan.created_at < next_day,
    )

    total_plans = query.count()
    if total_plans == 0:
        return 0.0

    completed_plans = query.filter(MaintenancePlan.status == "completed").count()

    return round(completed_plans / total_plans * 100, 2)


def generate_daily_report(db: Session, date_str: str = None, station_code: str = None) -> list:
    if not date_str:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")

    stations = []
    if station_code:
        stations = [station_code]
    else:
        station_objs = db.query(Station).all()
        stations = [s.station_code for s in station_objs]
        if not stations:
            stations = ["DEFAULT"]

    reports = []
    for sc in stations:
        existing = (
            db.query(OperationReport)
            .filter(
                OperationReport.report_date == date_str,
                OperationReport.station_code == sc,
            )
            .first()
        )
        if existing:
            reports.append(existing)
            continue

        marshalling_efficiency = calculate_marshalling_efficiency(db, date_str, sc)
        avg_stay_time = calculate_avg_stay_time(db, date_str, sc)
        maintenance_completion_rate = calculate_maintenance_completion_rate(db, date_str, sc)

        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        next_day = date_obj + timedelta(days=1)

        arrived_query = db.query(Vehicle).filter(
            Vehicle.arrived_at >= date_obj,
            Vehicle.arrived_at < next_day,
        )

        departed_query = db.query(Vehicle).filter(
            Vehicle.departed_at >= date_obj,
            Vehicle.departed_at < next_day,
        )

        maintenance_query = db.query(MaintenancePlan).filter(
            MaintenancePlan.created_at >= date_obj,
            MaintenancePlan.created_at < next_day,
        )

        container_query = db.query(Container).filter(
            Container.created_at >= date_obj,
            Container.created_at < next_day,
        )

        report = OperationReport(
            report_date=date_str,
            station_code=sc,
            marshalling_efficiency=marshalling_efficiency,
            avg_stay_time=avg_stay_time,
            maintenance_completion_rate=maintenance_completion_rate,
            total_arrived=arrived_query.count(),
            total_departed=departed_query.count(),
            total_maintenance=maintenance_query.count(),
            total_containers_handled=container_query.count(),
        )
        db.add(report)
        reports.append(report)

    db.commit()
    for r in reports:
        db.refresh(r)

    push_status_notification(
        db,
        title=f"运营报表生成 - {date_str}",
        content=f"{date_str} 运营报表已生成，共 {len(reports)} 个场站",
        notification_type="report",
        related_type="report",
        related_id=None,
        roles=["dispatcher"],
        priority="normal",
    )

    return reports


def get_reports(
    db: Session,
    start_date: str = None,
    end_date: str = None,
    station_code: str = None,
    skip: int = 0,
    limit: int = 50,
) -> list:
    query = db.query(OperationReport)
    if start_date:
        query = query.filter(OperationReport.report_date >= start_date)
    if end_date:
        query = query.filter(OperationReport.report_date <= end_date)
    if station_code:
        query = query.filter(OperationReport.station_code == station_code)
    return query.order_by(OperationReport.report_date.desc()).offset(skip).limit(limit).all()


def export_reports(db: Session, request: ReportExportRequest) -> dict:
    reports = get_reports(db, request.start_date, request.end_date, request.station_code)

    csv_rows = [
        "日期,场站,编组效率(%),平均停留时间(小时),检修完成率(%),到达总数,发车总数,检修总数,集装箱处理数,生成时间"
    ]
    for r in reports:
        csv_rows.append(
            f"{r.report_date},{r.station_code},{r.marshalling_efficiency},{r.avg_stay_time},"
            f"{r.maintenance_completion_rate},{r.total_arrived},{r.total_departed},"
            f"{r.total_maintenance},{r.total_containers_handled},{r.generated_at}"
        )

    csv_content = "\n".join(csv_rows)

    return {
        "success": True,
        "count": len(reports),
        "format": "csv",
        "content": csv_content,
        "filename": f"operation_report_{request.start_date}_{request.end_date}.csv",
    }
