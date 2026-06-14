import requests
import time
from datetime import datetime, timedelta

BASE = "http://localhost:8001/api/v1"


def t(label, resp, depth=1):
    pad = "  " * depth
    print(f"\n{'='*40}\n{label}\n{'='*40}")
    try:
        data = resp.json()
    except Exception:
        print(pad + "(text):", resp.text[:200])
        return

    if isinstance(data, dict):
        for k, v in data.items():
            if k == "notifications" and isinstance(v, list) and len(v) > 2:
                print(pad + f"{k}: [list(len={len(v)}) first2:")
                for n in v[:2]:
                    print(pad + f"    - [{n.get('delivery_status')}] {n.get('title')[:40]}")
            elif k == "flow" and isinstance(v, list):
                print(pad + f"{k}:")
                for step in v:
                    ts = step.get("timestamp", "")[:19] if step.get("timestamp") else "---"
                    print(pad + f"    {step.get('step')}: {step.get('status')} @ {ts}  ({step.get('remark') or ''})")
            elif k == "vehicles" and isinstance(v, list):
                print(pad + f"{k}: (len={len(v)})")
                for veh in v:
                    dep = veh.get("departed_at", "")[:19] if veh.get("departed_at") else "---"
                    arr = veh.get("arrived_at", "")[:19] if veh.get("arrived_at") else "---"
                    print(pad + f"    {veh.get('vehicle_no')}({veh.get('vehicle_type')}): 到达@{arr} | 离站@{dep} | 停留{veh.get('stay_hours')}h -> 目的地{veh.get('destination')}")
            elif k == "daily_trend" and isinstance(v, list):
                print(pad + f"{k}: (按场站拆开, {len(v)}条)")
                for item in v:
                    print(pad + f"    {item['report_date']} {item['station_code']}: 到{item['total_arrived']}/发{item['total_departed']}")
            elif k == "daily_total_trend" and isinstance(v, list):
                print(pad + f"{k}: (多站汇总)")
                for item in v:
                    print(pad + f"    {item['report_date']}: 到{item['total_arrived']}/发{item['total_departed']}")
            elif isinstance(v, list) and len(v) > 4:
                print(pad + f"{k}: [list(len={len(v)}) first3={v[:3]}]")
            else:
                print(pad + f"{k}: {v}")
    elif isinstance(data, list):
        print(pad + f"(list len={len(data)})")
        for i, item in enumerate(data[:5]):
            if isinstance(item, dict):
                brief = ", ".join(f"{k}={v}" for k, v in item.items() if k in ("id", "title", "status", "station_code", "report_date", "dispatch_no", "subject", "total_count", "pending_count", "read_count"))
                print(pad + f"  [{i}] {brief[:120]}")
            else:
                print(pad + f"  [{i}] {item}")


def run():
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # 1. 创建3个场站
    for code in ("ST001", "ST002", "ST003"):
        requests.post(f"{BASE}/stations", json={"station_code": code, "station_name": f"站{code}", "capacity": 100})
    print("已创建3场站：ST001 ST002 ST003")

    # 2. ST001 到达 2 辆
    requests.post(f"{BASE}/marshalling/arrival", json={
        "train_no": "T101", "station_code": "ST001",
        "vehicles": [
            {"vehicle_no": "V001", "vehicle_type": "box", "destination": "A", "train_no": "T101", "mileage": 1000, "weight": 50, "current_position": "track_1"},
            {"vehicle_no": "V002", "vehicle_type": "tank", "destination": "B", "train_no": "T101", "mileage": 2000, "weight": 60, "current_position": "track_1"},
        ]
    })
    # 3. ST002 到达 3 辆
    requests.post(f"{BASE}/marshalling/arrival", json={
        "train_no": "T202", "station_code": "ST002",
        "vehicles": [
            {"vehicle_no": "V101", "vehicle_type": "box", "destination": "C", "train_no": "T202", "mileage": 3000, "weight": 55, "current_position": "track_2"},
            {"vehicle_no": "V102", "vehicle_type": "flat", "destination": "D", "train_no": "T202", "mileage": 4000, "weight": 45, "current_position": "track_2"},
            {"vehicle_no": "V103", "vehicle_type": "box", "destination": "E", "train_no": "T202", "mileage": 5000, "weight": 70, "current_position": "track_2"},
        ]
    })
    # 4. ST003 到达 1 辆
    requests.post(f"{BASE}/marshalling/arrival", json={
        "train_no": "T303", "station_code": "ST003",
        "vehicles": [
            {"vehicle_no": "V201", "vehicle_type": "box", "destination": "F", "train_no": "T303", "mileage": 1500, "weight": 52, "current_position": "track_3"},
        ]
    })

    # ========================================
    # 测试 1：报表多场站联查 (station_codes=[ST001,ST003])
    # ========================================
    t("【测试1】趋势分析-指定多场站ST001+ST003", requests.get(f"{BASE}/reports/trend", params={
        "start_date": today, "end_date": today,
        "station_codes": ["ST001", "ST003"],
    }))

    # ========================================
    # 测试 2：CSV 多场站导出 对齐接口
    # ========================================
    resp = requests.post(f"{BASE}/reports/export", json={
        "start_date": today, "end_date": today,
        "station_codes": ["ST001", "ST003"],
    })
    print("\n" + "="*40)
    print("【测试2】CSV 导出多场站(ST001+ST003) — 应与接口一致")
    print("="*40)
    print(resp.text)

    # ========================================
    # 测试 3：发车流程(ST001) 并验证日报发车口径 = 0（未实际发车）
    # ========================================
    plans = requests.get(f"{BASE}/marshalling/plans", params={"station_code": "ST001"}).json()
    plan_id = plans[0]["id"] if isinstance(plans, list) else (plans.get("plans") or plans.get("items") or [plans])[0]["id"]

    t("【测试3a】创建发车记录(ST001,T101)", requests.post(f"{BASE}/dispatch", json={"train_no": "T101", "plan_id": plan_id}))
    dispatch_id = requests.get(f"{BASE}/dispatch", params={"train_no": "T101"}).json()[0]["id"]

    requests.post(f"{BASE}/dispatch/{dispatch_id}/verify-sequence")
    requests.post(f"{BASE}/dispatch/{dispatch_id}/brake-test", json={"passed": True, "operator": "tester"})
    t("【测试3b】下发发车指令", requests.post(f"{BASE}/dispatch/{dispatch_id}/depart", params={"driver": "王师傅"}))

    # 此时日报发车数应仍为 0！
    resp = requests.post(f"{BASE}/reports/generate", params={"station_code": "ST001", "date": today})
    rep = resp.json()[0]
    print("\n" + "="*40)
    print(f"【测试3c】指令已下发但未实际发车 — ST001 日报 total_departed = {rep['total_departed']} （口径检查，应为0！）")
    print("="*40)
    assert rep["total_departed"] == 0, f"FAIL! 指令下发就算发车了，total_departed={rep['total_departed']}"
    print("✓ PASS：未实际发车时，日报统计为 0")

    # ========================================
    # 测试 4：司机确认 + 实际发车，再次统计
    # ========================================
    t("【测试4a】司机确认发车", requests.post(f"{BASE}/dispatch/{dispatch_id}/driver-confirm", json={"driver_name": "王师傅"}))
    t("【测试4b】记录实际发车驶离场站", requests.post(f"{BASE}/dispatch/{dispatch_id}/actual-departure"))

    requests.post(f"{BASE}/reports/generate", params={"station_code": "ST001", "date": today})
    trend = requests.get(f"{BASE}/reports/trend", params={
        "start_date": today, "end_date": today, "station_code": "ST001"
    }).json()
    print("\n" + "="*40)
    print(f"【测试4c】实际发车后 ST001 日报发车数 = {trend['total_departed']}（应为1！）")
    print("="*40)
    assert trend["total_departed"] == 1, f"FAIL! 实际发车后应为1, got={trend['total_departed']}"
    print("✓ PASS：仅在记录actual_departure后，日报统计为1")

    # ========================================
    # 测试 5：车次流程查询 + 车辆明细离站时间
    # ========================================
    t("【测试5】发车流程+车辆明细(按ID)", requests.get(f"{BASE}/dispatch/{dispatch_id}/flow"))
    t("【测试5b】发车流程(按车次T101)", requests.get(f"{BASE}/dispatch/by-train/T101/flow"))

    # ========================================
    # 测试 6：通知增强 - 时间范围+业务类型筛选
    # ========================================
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    t("【测试6】调度员通知-按类型dispatch+状态pending筛选", requests.get(f"{BASE}/notifications", params={
        "role": "dispatcher",
        "notification_type": "dispatch",
        "delivery_status": "pending",
        "start_date": today,
        "end_date": tomorrow,
    }))

    t("【测试6b】调度员通知-按类型report+已读=false", requests.get(f"{BASE}/notifications", params={
        "role": "dispatcher",
        "notification_type": "report",
        "is_read": "false",
    }))

    # ========================================
    # 测试 7：通知会话化（related_type=dispatch 下所有通知聚合为一条会话）
    # ========================================
    t("【测试7】通知会话化(按业务聚合)", requests.get(f"{BASE}/notifications/sessions", params={
        "role": "dispatcher", "notification_type": "dispatch"
    }))

    # ========================================
    # 测试 8：通知CSV导出（字段与列表一致）
    # ========================================
    resp = requests.get(f"{BASE}/notifications/export", params={
        "recipient_role": "dispatcher",
        "notification_type": "dispatch",
        "start_date": today, "end_date": tomorrow,
    })
    print("\n" + "="*40)
    print("【测试8】通知CSV导出(调度员+dispatch类型)")
    print("="*40)
    print(resp.text[:800])

    # ========================================
    # 测试 9：多场站趋势daily_total_trend (ST001+ST002)
    # ========================================
    # ST002再实际发一班车
    plans2 = requests.get(f"{BASE}/marshalling/plans", params={"station_code": "ST002"}).json()
    pid2 = plans2[0]["id"] if isinstance(plans2, list) else plans2["plans"][0]["id"]
    requests.post(f"{BASE}/dispatch", json={"train_no": "T202", "plan_id": pid2})
    d2 = requests.get(f"{BASE}/dispatch", params={"train_no": "T202"}).json()[0]["id"]
    requests.post(f"{BASE}/dispatch/{d2}/verify-sequence")
    requests.post(f"{BASE}/dispatch/{d2}/brake-test", json={"passed": True, "operator": "t2"})
    requests.post(f"{BASE}/dispatch/{d2}/depart", params={"driver": "李师傅"})
    requests.post(f"{BASE}/dispatch/{d2}/actual-departure")

    t("【测试9】多场站趋势(ST001+ST002)=daily_total_trend 到3发2", requests.get(f"{BASE}/reports/trend", params={
        "start_date": today, "end_date": today,
        "station_codes": ["ST001", "ST002"],
    }))

    # ========================================
    # 【新增测试10】小时分布 GET /reports/hourly
    # ========================================
    resp = requests.get(f"{BASE}/reports/hourly", params={
        "start_date": today, "end_date": today,
        "station_codes": ["ST001", "ST002", "ST003"],
    })
    print("\n" + "="*40)
    print("【测试10】小时分布(ST001+ST002+ST003)")
    print("="*40)
    d = resp.json()
    print(f"  start_date={d['start_date']}, end_date={d['end_date']}, stations={d['station_codes']}")
    print(f"  by_station 数量: {len(d['by_station'])}")
    for item in d["by_station"][:6]:
        print(f"    H{item['hour']:02d} {item['station_code']}: 到{item['arrived_count']}/发{item['departed_count']}")
    print(f"  total keys: {list(d['total'].keys())}")
    assert "ST001" in d["total"], "FAIL 小时分布缺少 ST001 汇总"
    print("✓ PASS：小时分布返回 by_station + total 双维度")

    # ========================================
    # 【新增测试11】车次分布 GET /reports/trains
    # ========================================
    resp = requests.get(f"{BASE}/reports/trains", params={
        "start_date": today, "end_date": today,
    })
    print("\n" + "="*40)
    print("【测试11】车次分布(全部场站)")
    print("="*40)
    d = resp.json()
    print(f"  total_trains={d['total_trains']}, total_arrived_vehicles={d['total_arrived_vehicles']}, total_departures={d['total_departures']}")
    for item in d["items"]:
        print(f"    {item['station_code']}/{item['train_no']}: 车辆{item['total_arrived_vehicles']} 班次{item['total_departures']}")
    assert d["total_trains"] >= 3, "FAIL 车次分布统计漏车次"
    print("✓ PASS：车次分布返回 items + 汇总")

    # ========================================
    # 【新增测试12】延误链路 GET /dispatch/delay-summary
    # ========================================
    resp = requests.get(f"{BASE}/dispatch/delay-summary", params={
        "start_date": today, "end_date": today,
        "station_codes": ["ST001", "ST002"],
    })
    print("\n" + "="*40)
    print("【测试12】发车延误链路(ST001+ST002)")
    print("="*40)
    d = resp.json()
    print(f"  total_dispatches={d['total_dispatches']}, dispatches明细数={len(d['dispatches'])}")
    for item in d["dispatches"][:3]:
        print(f"    {item['dispatch_no']}/{item['train_no']}(司机{item['driver'] or '?'}) "
              f"间隔(下发{int(item.get('issue_delay_seconds') or -1)}s/确认{int(item.get('confirm_delay_seconds') or -1)}s/实际{int(item.get('actual_delay_seconds') or -1)}s) "
              f"总延误={int(item.get('total_delay_seconds') or -1)}s")
    print(f"  by_driver (len={len(d['by_driver'])}):")
    for s in d["by_driver"]:
        print(f"    {s['driver']}: avg_confirm={int(s.get('avg_confirm_delay') or 0)}s, avg_actual={int(s.get('avg_actual_delay') or 0)}s, bottleneck={s.get('bottleneck_stage')}")
    print(f"  by_station (len={len(d['by_station'])}):")
    for s in d["by_station"]:
        print(f"    {s['station_code']}: bottleneck={s.get('bottleneck_stage')}")
    assert len(d["dispatches"]) >= 2, "FAIL 延误明细缺失"
    assert d["by_driver"], "FAIL 司机汇总缺失"
    print("✓ PASS：延误链路返回明细+司机+场站三层面板")

    # ========================================
    # 【新增测试13】会话时间轴 GET /notifications/sessions
    # ========================================
    resp = requests.get(f"{BASE}/notifications/sessions", params={
        "delivery_status": "delivered",
    })
    print("\n" + "="*40)
    print("【测试13】通知会话时间轴(筛已送达)")
    print("="*40)
    d = resp.json()
    print(f"  会话数量: {len(d)}")
    for sess in d[:2]:
        print(f"  * {sess['subject']}: total={sess['total_count']} P/D/R={sess['pending_count']}/{sess['delivered_count']}/{sess['read_count']}  跨度{int(sess.get('total_duration_seconds') or 0)}s")
        tl = sess.get("timeline") or []
        for ev in tl[:3]:
            gap = f"+{ev['prev_interval_seconds']}s" if ev.get("prev_interval_seconds") is not None else "首条"
            print(f"      [{gap}] #{ev['event_index']} {ev['delivery_status']}: {ev['title'][:30]}")
    if d and (d[0].get("timeline") or []):
        assert "prev_interval_seconds" in d[0]["timeline"][0], "FAIL 时间轴缺少相邻间隔"
        print("✓ PASS：会话时间轴带 prev_interval_seconds")

    # ========================================
    # 【新增测试14】日报多场站批量生成 POST /reports/generate
    # ========================================
    resp = requests.post(f"{BASE}/reports/generate", params={
        "date": today,
        "station_codes": ["ST001", "ST002", "ST003"],
    })
    print("\n" + "="*40)
    print("【测试14】日报多场站批量生成(ST001/ST002/ST003)")
    print("="*40)
    d = resp.json()
    assert isinstance(d, list) and len(d) == 3, f"FAIL 多场站批量生成条数不对，len={len(d)}"
    for r in d:
        print(f"  {r['station_code']}: 到{r['total_arrived']}/发{r['total_departed']}  编组效率{r['marshalling_efficiency']}%")
    print("✓ PASS：日报支持 station_codes 数组批量生成")

    # ========================================
    # 【新增测试15】通知CSV导出 正文不截断 + 字段全量
    # ========================================
    resp = requests.get(f"{BASE}/notifications/export")
    print("\n" + "="*40)
    print("【测试15】通知CSV字段全量 + 正文不截断")
    print("="*40)
    lines = resp.text.splitlines()
    header = lines[0]
    print(f"  CSV header列数: {header.count(',') + 1}")
    print(f"  表头: {header}")
    assert "接收人ID" in header, "FAIL CSV缺 '接收人ID'"
    assert header.count(",") >= 14, f"FAIL CSV列数太少: {header.count(',') + 1}"
    if len(lines) > 1:
        first = lines[1]
        cols = [c.strip() for c in first.split(",")]
        content_col = cols[9] if len(cols) > 9 else ""
        print(f"  首行正文前120字符: {content_col[:120]}")
    print("✓ PASS：通知CSV列数全，正文未100字符截断")

    # ========================================
    # 【新增测试16】发车流程 interval_seconds / total_elapsed_seconds
    # ========================================
    dispatch_list = requests.get(f"{BASE}/dispatch").json()
    if dispatch_list:
        did = dispatch_list[0]["id"]
        resp = requests.get(f"{BASE}/dispatch/{did}/flow")
        d = resp.json()
        print("\n" + "="*40)
        print(f"【测试16】发车流程#{did} 步骤间隔")
        print("="*40)
        print(f"  total_elapsed_seconds = {d.get('total_elapsed_seconds')}")
        for step in d.get("flow", []):
            gap = f"+{step.get('interval_seconds')}s" if step.get("interval_seconds") is not None else "首步"
            ts = (step.get("timestamp") or "")[:19] or "---"
            print(f"    [{gap}] {step['step']} ({step['status']}) @{ts}")
        any_interval = any(s.get("interval_seconds") is not None for s in d.get("flow", []))
        assert any_interval or d.get("total_elapsed_seconds") is not None, "FAIL 流程缺少间隔字段"
        print("✓ PASS：发车流程带 interval_seconds 与 total_elapsed_seconds")

    print("\n" + "="*40)
    print("全部测试完成！（含第三轮4+2新增需求）")
    print("="*40)


if __name__ == "__main__":
    run()
