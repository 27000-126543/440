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
    print("\n" + "="*40)
    print("全部测试完成！")
    print("="*40)


if __name__ == "__main__":
    run()
