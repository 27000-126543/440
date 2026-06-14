from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import List, Optional

from app.models.models import (
    OperationReport,
    Vehicle,
    MarshallingPlan,
    MarshallingEntry,
    MaintenancePlan,
    Container,
    Station,
    TrainDispatch,
)
from app.schemas.report import (
    ReportExportRequest,
    DailyTrendItem,
    DailyTotalTrendItem,
    TrendSummary,
)
from app.services.notification_service import push_status_notification


def _date_range(start_date: str, end_date: str):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    cursor = start
    while cursor <= end:
        yield cursor.strftime("%Y-%m-%d")
        cursor += timedelta(days=1)


def _parse_station_codes(
    db: Session,
    station_code: Optional[str],
    station_codes: Optional[List[str]],
) -> List[str]:
    codes: List[str] = []
    if station_codes:
        codes = [s for s in station_codes if s]
    elif station_code:
        codes = [station_code]
    if not codes:
        station_objs = db.query(Station).all()
        codes = [s.station_code for s in station_objs]
    return codes if codes else ["DEFAULT"]


def calculate_marshalling_efficiency(db: Session, date_str: str, station_code: str) -> float:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    query = db.query(MarshallingPlan).filter(
        MarshallingPlan.created_at >= date_obj,
        MarshallingPlan.created_at < next_day,
        MarshallingPlan.station_code == station_code,
    )

    total_plans = query.count()
    if total_plans == 0:
        return 0.0

    completed_plans = query.filter(MarshallingPlan.status.in_(["completed", "departed"])).count()

    return round(completed_plans / total_plans * 100, 2)


def calculate_avg_stay_time(db: Session, date_str: str, station_code: str) -> float:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    query = db.query(Vehicle).filter(
        Vehicle.departed_at >= date_obj,
        Vehicle.departed_at < next_day,
        Vehicle.station_code == station_code,
        Vehicle.arrived_at != None,
    )

    vehicles = query.all()
    if not vehicles:
        return 0.0

    total_hours = 0.0
    for v in vehicles:
        stay_hours = (v.departed_at - v.arrived_at).total_seconds() / 3600
        total_hours += stay_hours

    return round(total_hours / len(vehicles), 2)


def calculate_maintenance_completion_rate(db: Session, date_str: str, station_code: str) -> float:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    query = db.query(MaintenancePlan).filter(
        MaintenancePlan.created_at >= date_obj,
        MaintenancePlan.created_at < next_day,
        MaintenancePlan.station_code == station_code,
    )

    total_plans = query.count()
    if total_plans == 0:
        return 0.0

    completed_plans = query.filter(MaintenancePlan.status == "completed").count()

    return round(completed_plans / total_plans * 100, 2)


def count_arrived_vehicles(db: Session, date_str: str, station_code: str) -> int:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    return (
        db.query(Vehicle)
        .filter(
            Vehicle.arrived_at >= date_obj,
            Vehicle.arrived_at < next_day,
            Vehicle.station_code == station_code,
        )
        .count()
    )


def count_departed_vehicles(db: Session, date_str: str, station_code: str) -> int:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    return (
        db.query(Vehicle)
        .filter(
            Vehicle.departed_at >= date_obj,
            Vehicle.departed_at < next_day,
            Vehicle.station_code == station_code,
        )
        .count()
    )


def count_actual_dispatches(db: Session, date_str: str, station_code: str) -> int:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    return (
        db.query(TrainDispatch)
        .join(MarshallingPlan, TrainDispatch.plan_id == MarshallingPlan.id)
        .filter(
            TrainDispatch.actual_departure_time >= date_obj,
            TrainDispatch.actual_departure_time < next_day,
            MarshallingPlan.station_code == station_code,
        )
        .count()
    )


def count_maintenance_plans(db: Session, date_str: str, station_code: str) -> int:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    return (
        db.query(MaintenancePlan)
        .filter(
            MaintenancePlan.created_at >= date_obj,
            MaintenancePlan.created_at < next_day,
            MaintenancePlan.station_code == station_code,
        )
        .count()
    )


def count_containers(db: Session, date_str: str, station_code: str) -> int:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    next_day = date_obj + timedelta(days=1)

    return (
        db.query(Container)
        .filter(
            Container.created_at >= date_obj,
            Container.created_at < next_day,
            Container.station_code == station_code,
        )
        .count()
    )


def generate_daily_report(
    db: Session,
    date_str: str = None,
    station_code: str = None,
    station_codes: Optional[List[str]] = None,
) -> list:
    if not date_str:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")

    stations = _parse_station_codes(db, station_code, station_codes)

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

        report_data = dict(
            report_date=date_str,
            station_code=sc,
            marshalling_efficiency=calculate_marshalling_efficiency(db, date_str, sc),
            avg_stay_time=calculate_avg_stay_time(db, date_str, sc),
            maintenance_completion_rate=calculate_maintenance_completion_rate(db, date_str, sc),
            total_arrived=count_arrived_vehicles(db, date_str, sc),
            total_departed=count_actual_dispatches(db, date_str, sc),
            total_maintenance=count_maintenance_plans(db, date_str, sc),
            total_containers_handled=count_containers(db, date_str, sc),
        )

        if existing:
            for k, v in report_data.items():
                setattr(existing, k, v)
            report = existing
        else:
            report = OperationReport(generated_at=datetime.utcnow(), **report_data)
            db.add(report)
        reports.append(report)

    db.commit()
    for r in reports:
        db.refresh(r)

    push_status_notification(
        db,
        title=f"运营报表生成 - {date_str}",
        content=f"{date_str} 运营报表已生成，共 {len(reports)} 个场站（含 {','.join(stations)}）",
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
    station_codes: Optional[List[str]] = None,
    skip: int = 0,
    limit: int = 50,
) -> list:
    query = db.query(OperationReport)
    if start_date:
        query = query.filter(OperationReport.report_date >= start_date)
    if end_date:
        query = query.filter(OperationReport.report_date <= end_date)
    codes = _parse_station_codes(db, station_code, station_codes) if (station_code or station_codes or True) else None
    if codes:
        query = query.filter(OperationReport.station_code.in_(codes))
    return query.order_by(OperationReport.report_date.desc(), OperationReport.station_code).offset(skip).limit(limit).all()


def get_trend_summary(
    db: Session,
    start_date: str,
    end_date: str,
    station_code: Optional[str] = None,
    station_codes: Optional[List[str]] = None,
) -> TrendSummary:
    stations = _parse_station_codes(db, station_code, station_codes)

    daily_trend: List[DailyTrendItem] = []
    daily_total_map = {}

    total_arrived = 0
    total_departed = 0
    total_maintenance = 0
    total_containers = 0
    marshalling_sum = 0.0
    stay_sum = 0.0
    maintenance_sum = 0.0
    valid_days = 0

    for date_str in _date_range(start_date, end_date):
        day_arrived = 0
        day_departed = 0
        day_maint = 0
        day_containers = 0
        day_marshalling_sum = 0.0
        day_stay_sum = 0.0
        day_maint_rate_sum = 0.0
        stations_count = 0

        for sc in stations:
            arrived = count_arrived_vehicles(db, date_str, sc)
            departed = count_actual_dispatches(db, date_str, sc)
            maint = count_maintenance_plans(db, date_str, sc)
            containers = count_containers(db, date_str, sc)
            marshalling_eff = calculate_marshalling_efficiency(db, date_str, sc)
            stay = calculate_avg_stay_time(db, date_str, sc)
            maint_rate = calculate_maintenance_completion_rate(db, date_str, sc)

            total_arrived += arrived
            total_departed += departed
            total_maintenance += maint
            total_containers += containers
            marshalling_sum += marshalling_eff
            stay_sum += stay
            maintenance_sum += maint_rate
            valid_days += 1

            day_arrived += arrived
            day_departed += departed
            day_maint += maint
            day_containers += containers
            day_marshalling_sum += marshalling_eff
            day_stay_sum += stay
            day_maint_rate_sum += maint_rate
            stations_count += 1

            daily_trend.append(DailyTrendItem(
                report_date=date_str,
                station_code=sc,
                total_arrived=arrived,
                total_departed=departed,
                marshalling_efficiency=marshalling_eff,
                avg_stay_time=stay,
                maintenance_completion_rate=maint_rate,
                total_maintenance=maint,
                total_containers_handled=containers,
            ))

        avg_day_marshalling = round(day_marshalling_sum / stations_count, 2) if stations_count > 0 else 0.0
        avg_day_stay = round(day_stay_sum / stations_count, 2) if stations_count > 0 else 0.0
        avg_day_maint = round(day_maint_rate_sum / stations_count, 2) if stations_count > 0 else 0.0

        daily_total_map[date_str] = DailyTotalTrendItem(
            report_date=date_str,
            total_arrived=day_arrived,
            total_departed=day_departed,
            avg_marshalling_efficiency=avg_day_marshalling,
            avg_stay_time=avg_day_stay,
            avg_maintenance_completion_rate=avg_day_maint,
            total_maintenance=day_maint,
            total_containers_handled=day_containers,
        )

    avg_marshalling = round(marshalling_sum / valid_days, 2) if valid_days > 0 else 0.0
    avg_stay = round(stay_sum / valid_days, 2) if valid_days > 0 else 0.0
    avg_maintenance = round(maintenance_sum / valid_days, 2) if valid_days > 0 else 0.0

    daily_total_trend = [daily_total_map[d] for d in _date_range(start_date, end_date)]

    return TrendSummary(
        start_date=start_date,
        end_date=end_date,
        station_codes=stations,
        total_arrived=total_arrived,
        total_departed=total_departed,
        avg_marshalling_efficiency=avg_marshalling,
        avg_stay_time=avg_stay,
        avg_maintenance_completion_rate=avg_maintenance,
        total_maintenance=total_maintenance,
        total_containers_handled=total_containers,
        daily_trend=daily_trend,
        daily_total_trend=daily_total_trend,
    )


def export_reports(db: Session, request: ReportExportRequest) -> dict:
    summary = get_trend_summary(
        db, request.start_date, request.end_date, request.station_code, request.station_codes
    )

    csv_rows = [
        "日期,场站,编组效率(%),平均停留时间(小时),检修完成率(%),到达总数,实际发车数,检修总数,集装箱处理数"
    ]
    for item in summary.daily_trend:
        csv_rows.append(
            f"{item.report_date},{item.station_code},{item.marshalling_efficiency},{item.avg_stay_time},"
            f"{item.maintenance_completion_rate},{item.total_arrived},{item.total_departed},"
            f"{item.total_maintenance},{item.total_containers_handled}"
        )

    csv_rows.append("")
    csv_rows.append(
        "日期,场站范围,平均编组效率(%),平均停留时间(小时),平均检修完成率(%),到达总数,实际发车总数,检修总数,集装箱处理总数"
    )
    for tot in summary.daily_total_trend:
        csv_rows.append(
            f"{tot.report_date},MULTI({len(summary.station_codes)}站),{tot.avg_marshalling_efficiency},"
            f"{tot.avg_stay_time},{tot.avg_maintenance_completion_rate},{tot.total_arrived},"
            f"{tot.total_departed},{tot.total_maintenance},{tot.total_containers_handled}"
        )

    csv_rows.append("")
    csv_rows.append(
        f"区间汇总,{','.join(summary.station_codes)},{summary.avg_marshalling_efficiency},"
        f"{summary.avg_stay_time},{summary.avg_maintenance_completion_rate},"
        f"{summary.total_arrived},{summary.total_departed},"
        f"{summary.total_maintenance},{summary.total_containers_handled}"
    )

    csv_content = "\n".join(csv_rows)

    suffix = f"_{request.station_code}" if request.station_code else (
        f"_MULTI_{len(request.station_codes)}st" if request.station_codes else "_ALL"
    )
    return {
        "success": True,
        "count": len(summary.daily_trend),
        "format": "csv",
        "content": csv_content,
        "filename": f"operation_report_trend{suffix}_{request.start_date}_{request.end_date}.csv",
    }
