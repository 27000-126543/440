import requests
import time
from datetime import datetime, timedelta

BASE = "http://localhost:8001/api/v1"


def t(label, resp):
    print(f"\n=== {label} ===")
    try:
        data = resp.json()
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list) and len(v) > 3:
                    print(f"  {k}: [{', '.join(str(x) for x in v[:3])} ...](len={len(v)})")
                else:
                    print(f"  {k}: {v}")
        elif isinstance(data, list):
            print(f"  (list len={len(data)})")
            for i, item in enumerate(data[:3]):
                print(f"  [{i}] {item}")
    except Exception as e:
        print("  (text):", resp.text[:200])


def run():
    # 1. 创建场站
    print("1. 创建场站")
    for code in ("ST001", "ST002"):
        requests.post(f"{BASE}/stations", json={"station_code": code, "station_name": f"测试站{code}", "capacity": 100})

    # 2. ST001到达2辆
    t("ST001到达车辆", requests.post(f"{BASE}/marshalling/arrival", json={
        "train_no": "T101",
        "station_code": "ST001",
        "vehicles": [
            {"vehicle_no": "V001", "vehicle_type": "box", "destination": "A", "train_no": "T101", "mileage": 1000, "weight": 50, "current_position": "track_1"},
            {"vehicle_no": "V002", "vehicle_type": "tank", "destination": "B", "train_no": "T101", "mileage": 2000, "weight": 60, "current_position": "track_1"},
        ]
    }))

    # 3. ST002到达3辆
    t("ST002到达车辆", requests.post(f"{BASE}/marshalling/arrival", json={
        "train_no": "T202",
        "station_code": "ST002",
        "vehicles": [
            {"vehicle_no": "V101", "vehicle_type": "box", "destination": "C", "train_no": "T202", "mileage": 3000, "weight": 55, "current_position": "track_2"},
            {"vehicle_no": "V102", "vehicle_type": "flat", "destination": "D", "train_no": "T202", "mileage": 4000, "weight": 45, "current_position": "track_2"},
            {"vehicle_no": "V103", "vehicle_type": "box", "destination": "E", "train_no": "T202", "mileage": 5000, "weight": 70, "current_position": "track_2"},
        ]
    }))

    # 4. 生成报表
    t("ST001报表", requests.post(f"{BASE}/reports/generate", params={"station_code": "ST001"}))
    t("ST002报表", requests.post(f"{BASE}/reports/generate", params={"station_code": "ST002"}))

    # 5. 趋势分析 - 按场站隔离
    today = datetime.utcnow().strftime("%Y-%m-%d")
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    t("趋势分析-ST001", requests.get(f"{BASE}/reports/trend", params={
        "start_date": today, "end_date": today, "station_code": "ST001"
    }))
    t("趋势分析-ST002", requests.get(f"{BASE}/reports/trend", params={
        "start_date": today, "end_date": today, "station_code": "ST002"
    }))

    # 6. CSV导出 - ST001
    resp = requests.post(f"{BASE}/reports/export", json={"start_date": today, "end_date": today, "station_code": "ST001"})
    print("\n=== CSV导出(ST001) ===")
    print(resp.text)

    # 7. 准备发车流程：直接用已有的plan ST001
    plans = requests.get(f"{BASE}/marshalling/plans", params={"station_code": "ST001"}).json()
    if isinstance(plans, dict):
        plans = plans.get("plans") or plans.get("items") or [plans]
    plan_id = plans[0]["id"] if plans else None
    if not plan_id:
        print("未找到编组计划，跳过发车测试")
        return

    # 标记编组计划状态为completed
    # 创建发车
    t("创建发车记录", requests.post(f"{BASE}/dispatch", json={"train_no": "T101", "plan_id": plan_id}))
    dispatches = requests.get(f"{BASE}/dispatch", params={"train_no": "T101"}).json()
    dispatch_id = dispatches[0]["id"]

    # 顺序校验会失败（因为车辆没标完成），直接手动改DB：通过HTTP直接调用完成
    # 用marshalling的plan完成接口
    t("顺序校验", requests.post(f"{BASE}/dispatch/{dispatch_id}/verify-sequence"))
    # 无论校验过没过，先测接口存在性；制动测试通过
    t("制动测试", requests.post(f"{BASE}/dispatch/{dispatch_id}/brake-test", json={"passed": True, "operator": "test"}))
    t("发车指令下发", requests.post(f"{BASE}/dispatch/{dispatch_id}/depart", params={"driver": "王师傅"}))
    t("司机确认", requests.post(f"{BASE}/dispatch/{dispatch_id}/driver-confirm", json={"driver_name": "王师傅"}))
    t("实际发车记录", requests.post(f"{BASE}/dispatch/{dispatch_id}/actual-departure"))

    # 8. 发车流程追踪
    t("发车流程追踪(按ID)", requests.get(f"{BASE}/dispatch/{dispatch_id}/flow"))
    t("发车流程追踪(按车次)", requests.get(f"{BASE}/dispatch/by-train/T101/flow"))

    # 9. 司机通知
    t("司机通知列表", requests.get(f"{BASE}/drivers/王师傅/notifications"))
    t("司机未读数", requests.get(f"{BASE}/drivers/王师傅/notifications/unread-count"))

    # 10. 消息ACK - 批量已送达
    notifs = requests.get(f"{BASE}/drivers/王师傅/notifications").json()
    notif_ids = [n["id"] for n in notifs]
    t("批量ACK-已送达", requests.post(f"{BASE}/drivers/王师傅/notifications/ack", json={
        "notification_ids": notif_ids, "ack_type": "delivered"
    }))
    t("批量ACK后状态", requests.get(f"{BASE}/drivers/王师傅/notifications"))

    # 11. 标记已读
    if notif_ids:
        t("标已读", requests.post(f"{BASE}/notifications/{notif_ids[0]}/read"))

    # 12. 调度员通知含pending/已送达/已读
    t("调度员未读数(含pending)", requests.get(f"{BASE}/notifications/unread-count", params={"role": "dispatcher"}))
    t("调度员通知(按状态pending)", requests.get(f"{BASE}/notifications", params={"role": "dispatcher", "delivery_status": "pending", "limit": 3}))


if __name__ == "__main__":
    run()
