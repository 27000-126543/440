from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

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
    HourlyDistributionItem,
    HourlyDistributionSummary,
    TrainDistributionItem,
    TrainDistributionSummary,
    DispatchDelayItem,
    DispatchDelaySummary,
    DriverDelayStats,
    StationDelayStats,
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
    codes = _parse_station_codes(db, station_code, station_codes)
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
    daily_total_map: Dict[str, DailyTotalTrendItem] = {}

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


def get_hourly_distribution(
    db: Session,
    start_date: str,
    end_date: str,
    station_code: Optional[str] = None,
    station_codes: Optional[List[str]] = None,
) -> HourlyDistributionSummary:
    stations = _parse_station_codes(db, station_code, station_codes)
    sd = datetime.strptime(start_date, "%Y-%m-%d")
    ed = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

    by_station: List[HourlyDistributionItem] = []
    total_accum: Dict[str, Dict[str, int]] = {str(h): {"arrived_count": 0, "departed_count": 0} for h in range(24)}

    for sc in stations:
        arrived_q = (
            db.query(
                func.strftime("%H", Vehicle.arrived_at).label("hour"),
                func.count(Vehicle.id).label("cnt"),
            )
            .filter(
                Vehicle.arrived_at >= sd,
                Vehicle.arrived_at < ed,
                Vehicle.station_code == sc,
            )
            .group_by(func.strftime("%H", Vehicle.arrived_at))
            .all()
        )
        departed_q = (
            db.query(
                func.strftime("%H", TrainDispatch.actual_departure_time).label("hour"),
                func.count(TrainDispatch.id).label("cnt"),
            )
            .join(MarshallingPlan, TrainDispatch.plan_id == MarshallingPlan.id)
            .filter(
                TrainDispatch.actual_departure_time >= sd,
                TrainDispatch.actual_departure_time < ed,
                MarshallingPlan.station_code == sc,
            )
            .group_by(func.strftime("%H", TrainDispatch.actual_departure_time))
            .all()
        )
        a_map = {int(r.hour or 0): r.cnt for r in arrived_q}
        d_map = {int(r.hour or 0): r.cnt for r in departed_q}

        for h in range(24):
            ac = a_map.get(h, 0)
            dc = d_map.get(h, 0)
            by_station.append(HourlyDistributionItem(
                hour=h,
                station_code=sc,
                arrived_count=ac,
                departed_count=dc,
            ))
            total_accum[str(h)]["arrived_count"] += ac
            total_accum[str(h)]["departed_count"] += dc

    return HourlyDistributionSummary(
        start_date=start_date,
        end_date=end_date,
        station_codes=stations,
        by_station=by_station,
        total=total_accum,
    )


def get_train_distribution(
    db: Session,
    start_date: str,
    end_date: str,
    station_code: Optional[str] = None,
    station_codes: Optional[List[str]] = None,
) -> TrainDistributionSummary:
    stations = _parse_station_codes(db, station_code, station_codes)
    sd = datetime.strptime(start_date, "%Y-%m-%d")
    ed = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

    train_map: Dict[str, Dict[str, Any]] = {}

    arrived = (
        db.query(
            Vehicle.train_no,
            Vehicle.station_code,
            func.count(Vehicle.id).label("cnt"),
            func.min(Vehicle.arrived_at).label("first_arr"),
        )
        .filter(
            Vehicle.arrived_at >= sd,
            Vehicle.arrived_at < ed,
            Vehicle.station_code.in_(stations),
        )
        .group_by(Vehicle.train_no, Vehicle.station_code)
        .all()
    )
    for r in arrived:
        key = f"{r.station_code}:{r.train_no}"
        if key not in train_map:
            train_map[key] = {
                "station_code": r.station_code,
                "train_no": r.train_no,
                "total_arrived_vehicles": 0,
                "total_departures": 0,
                "first_arrival": None,
                "last_departure": None,
            }
        train_map[key]["total_arrived_vehicles"] = r.cnt
        train_map[key]["first_arrival"] = r.first_arr

    departed = (
        db.query(
            TrainDispatch.train_no,
            MarshallingPlan.station_code,
            func.count(TrainDispatch.id).label("cnt"),
            func.max(TrainDispatch.actual_departure_time).label("last_dep"),
        )
        .join(MarshallingPlan, TrainDispatch.plan_id == MarshallingPlan.id)
        .filter(
            TrainDispatch.actual_departure_time >= sd,
            TrainDispatch.actual_departure_time < ed,
            MarshallingPlan.station_code.in_(stations),
        )
        .group_by(TrainDispatch.train_no, MarshallingPlan.station_code)
        .all()
    )
    for r in departed:
        key = f"{r.station_code}:{r.train_no}"
        if key not in train_map:
            train_map[key] = {
                "station_code": r.station_code,
                "train_no": r.train_no,
                "total_arrived_vehicles": 0,
                "total_departures": 0,
                "first_arrival": None,
                "last_departure": None,
            }
        train_map[key]["total_departures"] = r.cnt
        train_map[key]["last_departure"] = r.last_dep

    items: List[TrainDistributionItem] = []
    total_trains = 0
    total_arrived_vehicles = 0
    total_departures = 0
    for t in train_map.values():
        items.append(TrainDistributionItem(**t))
        total_trains += 1
        total_arrived_vehicles += t["total_arrived_vehicles"]
        total_departures += t["total_departures"]

    items.sort(key=lambda x: (x.station_code, x.train_no))

    return TrainDistributionSummary(
        start_date=start_date,
        end_date=end_date,
        station_codes=stations,
        items=items,
        total_trains=total_trains,
        total_arrived_vehicles=total_arrived_vehicles,
        total_departures=total_departures,
    )


def get_dispatch_delay_summary(
    db: Session,
    start_date: str,
    end_date: str,
    station_code: Optional[str] = None,
    station_codes: Optional[List[str]] = None,
) -> DispatchDelaySummary:
    stations = _parse_station_codes(db, station_code, station_codes)
    sd = datetime.strptime(start_date, "%Y-%m-%d")
    ed = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

    dispatches = (
        db.query(TrainDispatch)
        .join(MarshallingPlan, TrainDispatch.plan_id == MarshallingPlan.id)
        .filter(
            TrainDispatch.created_at >= sd,
            TrainDispatch.created_at < ed,
            MarshallingPlan.station_code.in_(stations),
        )
        .all()
    )

    delay_items: List[DispatchDelayItem] = []
    driver_stats: Dict[str, Dict[str, Any]] = {}
    station_stats: Dict[str, Dict[str, Any]] = {}

    for d in dispatches:
        plan = db.query(MarshallingPlan).filter(MarshallingPlan.id == d.plan_id).first()
        sc = plan.station_code if plan else None
        base = d.scheduled_departure or d.created_at

        issue_delay = (d.departure_issued_at - base).total_seconds() if d.departure_issued_at else None
        confirm_delay = (d.driver_confirmed_at - d.departure_issued_at).total_seconds() if (d.driver_confirmed_at and d.departure_issued_at) else None
        actual_delay = (d.actual_departure_time - d.driver_confirmed_at).total_seconds() if (d.actual_departure_time and d.driver_confirmed_at) else None
        total_delay = (d.actual_departure_time - base).total_seconds() if (d.actual_departure_time) else None

        delay_items.append(DispatchDelayItem(
            dispatch_id=d.id,
            dispatch_no=d.dispatch_no,
            train_no=d.train_no,
            driver=d.driver,
            station_code=sc,
            scheduled_departure=d.scheduled_departure,
            departure_issued_at=d.departure_issued_at,
            driver_confirmed_at=d.driver_confirmed_at,
            actual_departure_time=d.actual_departure_time,
            issue_delay_seconds=issue_delay,
            confirm_delay_seconds=confirm_delay,
            actual_delay_seconds=actual_delay,
            total_delay_seconds=total_delay,
        ))

        if d.driver:
            if d.driver not in driver_stats:
                driver_stats[d.driver] = {
                    "total": 0, "confirm_sum": 0.0, "confirm_cnt": 0,
                    "actual_sum": 0.0, "actual_cnt": 0,
                }
            driver_stats[d.driver]["total"] += 1
            if confirm_delay is not None:
                driver_stats[d.driver]["confirm_sum"] += confirm_delay
                driver_stats[d.driver]["confirm_cnt"] += 1
            if actual_delay is not None:
                driver_stats[d.driver]["actual_sum"] += actual_delay
                driver_stats[d.driver]["actual_cnt"] += 1

        if sc:
            if sc not in station_stats:
                station_stats[sc] = {
                    "total": 0, "issue_sum": 0.0, "issue_cnt": 0,
                    "confirm_sum": 0.0, "confirm_cnt": 0,
                    "actual_sum": 0.0, "actual_cnt": 0,
                }
            station_stats[sc]["total"] += 1
            if issue_delay is not None:
                station_stats[sc]["issue_sum"] += issue_delay
                station_stats[sc]["issue_cnt"] += 1
            if confirm_delay is not None:
                station_stats[sc]["confirm_sum"] += confirm_delay
                station_stats[sc]["confirm_cnt"] += 1
            if actual_delay is not None:
                station_stats[sc]["actual_sum"] += actual_delay
                station_stats[sc]["actual_cnt"] += 1

    driver_list: List[DriverDelayStats] = []
    for driver, s in driver_stats.items():
        avg_c = round(s["confirm_sum"] / s["confirm_cnt"], 2) if s["confirm_cnt"] else 0.0
        avg_a = round(s["actual_sum"] / s["actual_cnt"], 2) if s["actual_cnt"] else 0.0
        if avg_c >= avg_a:
            bottleneck = "司机确认" if avg_c > 0 else "无明显瓶颈"
        else:
            bottleneck = "实际发车离站" if avg_a > 0 else "无明显瓶颈"
        driver_list.append(DriverDelayStats(
            driver=driver,
            total_dispatches=s["total"],
            avg_confirm_delay_seconds=avg_c,
            avg_actual_delay_seconds=avg_a,
            bottleneck_stage=bottleneck,
        ))

    station_list: List[StationDelayStats] = []
    for sc, s in station_stats.items():
        avg_i = round(s["issue_sum"] / s["issue_cnt"], 2) if s["issue_cnt"] else 0.0
        avg_c = round(s["confirm_sum"] / s["confirm_cnt"], 2) if s["confirm_cnt"] else 0.0
        avg_a = round(s["actual_sum"] / s["actual_cnt"], 2) if s["actual_cnt"] else 0.0
        stages = [("指令下发", avg_i), ("司机确认", avg_c), ("实际发车", avg_a)]
        max_stage = max(stages, key=lambda x: x[1])
        bottleneck = max_stage[0] if max_stage[1] > 0 else "无明显瓶颈"
        station_list.append(StationDelayStats(
            station_code=sc,
            total_dispatches=s["total"],
            avg_issue_delay_seconds=avg_i,
            avg_confirm_delay_seconds=avg_c,
            avg_actual_delay_seconds=avg_a,
            bottleneck_stage=bottleneck,
        ))

    return DispatchDelaySummary(
        start_date=start_date,
        end_date=end_date,
        station_codes=stations,
        total_dispatches=len(delay_items),
        dispatches=delay_items,
        by_driver=sorted(driver_list, key=lambda x: x.total_dispatches, reverse=True),
        by_station=sorted(station_list, key=lambda x: x.station_code),
    )


def export_reports(db: Session, request: ReportExportRequest) -> dict:
    summary = get_trend_summary(
        db, request.start_date, request.end_date, request.station_code, request.station_codes
    )
    hourly = get_hourly_distribution(
        db, request.start_date, request.end_date, request.station_code, request.station_codes
    )
    trains = get_train_distribution(
        db, request.start_date, request.end_date, request.station_code, request.station_codes
    )

    csv_rows = []
    csv_rows.append("=== 第一部分：每日运营趋势（按场站明细） ===")
    csv_rows.append(
        "日期,场站,编组效率(%),平均停留时间(小时),检修完成率(%),到达总数,实际发车数,检修总数,集装箱处理数"
    )
    for item in summary.daily_trend:
        csv_rows.append(
            f"{item.report_date},{item.station_code},{item.marshalling_efficiency},{item.avg_stay_time},"
            f"{item.maintenance_completion_rate},{item.total_arrived},{item.total_departed},"
            f"{item.total_maintenance},{item.total_containers_handled}"
        )

    csv_rows.append("")
    csv_rows.append("=== 第二部分：每日运营趋势（多站汇总） ===")
    csv_rows.append(
        "日期,场站数量,平均编组效率(%),平均停留时间(小时),平均检修完成率(%),到达总数,实际发车总数,检修总数,集装箱处理总数"
    )
    for tot in summary.daily_total_trend:
        csv_rows.append(
            f"{tot.report_date},{len(summary.station_codes)},{tot.avg_marshalling_efficiency},"
            f"{tot.avg_stay_time},{tot.avg_maintenance_completion_rate},"
            f"{tot.total_arrived},{tot.total_departed},{tot.total_maintenance},{tot.total_containers_handled}"
        )

    csv_rows.append("")
    csv_rows.append("=== 第三部分：小时分布（0-23时） ===")
    header = ["小时"] + [f"{sc}_到达" for sc in summary.station_codes] + [f"{sc}_发车" for sc in summary.station_codes] + ["合计_到达", "合计_发车"]
    csv_rows.append(",".join(header))
    for h in range(24):
        row = [str(h)]
        total_arr = 0
        total_dep = 0
        for sc in summary.station_codes:
            match = [x for x in hourly.by_station if x.hour == h and x.station_code == sc]
            arr = match[0].arrived_count if match else 0
            dep = match[0].departed_count if match else 0
            row.append(str(arr))
            row.append(str(dep))
            total_arr += arr
            total_dep += dep
        row.append(str(total_arr))
        row.append(str(total_dep))
        csv_rows.append(",".join(row))

    csv_rows.append("")
    csv_rows.append("=== 第四部分：车次分布 ===")
    csv_rows.append("场站,车次,到达车辆数,发车班次数,首车到达时间,末班车发车时间")
    for t in trains.items:
        csv_rows.append(
            f"{t.station_code},{t.train_no},{t.total_arrived_vehicles},{t.total_departures},"
            f"{t.first_arrival or ''},{t.last_departure or ''}"
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
        "filename": f"operation_report_full{suffix}_{request.start_date}_{request.end_date}.csv",
    }
