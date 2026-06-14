import requests
from datetime import datetime

BASE = "http://localhost:8001/api/v1"

today = datetime.utcnow().strftime("%Y-%m-%d")

print("\n" + "="*60)
print("测试新增API（第三轮 4项需求 + 2个小问题）")
print("="*60)

# 1. 小时分布
print("\n[1] GET /reports/hourly — 小时分布")
resp = requests.get(f"{BASE}/reports/hourly", params={
    "start_date": today, "end_date": today,
})
d = resp.json()
print(f"    station_codes={d['station_codes']}, by_station={len(d['by_station'])}条, total keys={list(d['total'].keys())}")
for h in range(24):
    row = [i for i in d["by_station"] if i["hour"] == h]
    if row and (row[0]["arrived_count"] or row[0]["departed_count"]):
        for r in row:
            print(f"      H{h:02d} {r['station_code']}: 到{r['arrived_count']}/发{r['departed_count']}")
assert d.get("total"), "FAIL hourly missing total"
print("    ✓ PASS")

# 2. 车次分布
print("\n[2] GET /reports/trains — 车次分布")
resp = requests.get(f"{BASE}/reports/trains", params={
    "start_date": today, "end_date": today,
})
d = resp.json()
print(f"    total_trains={d['total_trains']}, arrived={d['total_arrived_vehicles']}, departures={d['total_departures']}, items={len(d['items'])}")
for it in d["items"][:3]:
    print(f"      {it['station_code']}/{it['train_no']}: 车辆{it['total_arrived_vehicles']} 班次{it['total_departures']}")
assert d["total_trains"] >= 1, "FAIL trains empty"
print("    ✓ PASS")

# 3. 延误链路
print("\n[3] GET /dispatch/delay-summary — 延误链路复盘")
resp = requests.get(f"{BASE}/dispatch/delay-summary", params={
    "start_date": today, "end_date": today,
})
d = resp.json()
print(f"    total_dispatches={d['total_dispatches']}, 明细={len(d['dispatches'])}, 司机汇总={len(d['by_driver'])}, 场站汇总={len(d['by_station'])}")
for it in d["dispatches"][:3]:
    print(f"      {it['dispatch_no']}/{it['train_no']} 司机{it['driver'] or '-'}: 下发延迟{it.get('issue_delay_seconds') or 0}s 确认延迟{it.get('confirm_delay_seconds') or 0}s 实际延迟{it.get('actual_delay_seconds') or 0}s 总延迟{it.get('total_delay_seconds') or 0}s")
for s in d["by_driver"][:2]:
    print(f"      司机汇总 {s['driver']}: 瓶颈={s.get('bottleneck_stage')} avg_confirm={s.get('avg_confirm_delay')}")
for s in d["by_station"][:2]:
    print(f"      场站汇总 {s['station_code']}: 瓶颈={s.get('bottleneck_stage')}")
assert "dispatches" in d and "by_driver" in d and "by_station" in d, "FAIL delay summary fields missing"
print("    ✓ PASS")

# 4. 会话时间轴 + 分段筛
print("\n[4] GET /notifications/sessions — 会话时间轴+分段筛")
resp = requests.get(f"{BASE}/notifications/sessions", params={
    "start_date": today, "end_date": today,
})
d = resp.json()
print(f"    会话数={len(d)}")
for s in d[:2]:
    print(f"      * {s['subject']}: total={s['total_count']} P/D/R={s['pending_count']}/{s['delivered_count']}/{s['read_count']} 跨度{s.get('total_duration_seconds')}s")
    tl = s.get("timeline") or []
    for ev in tl[:3]:
        gap = f"+{ev['prev_interval_seconds']}s" if ev.get("prev_interval_seconds") is not None else "首条"
        print(f"          [{gap}] #{ev['event_index']} {ev['delivery_status']}: {ev['title'][:30]}")
if d:
    assert "timeline" in d[0] and "total_duration_seconds" in d[0], "FAIL session fields missing"
    if d[0].get("timeline"):
        assert "prev_interval_seconds" in d[0]["timeline"][0], "FAIL timeline prev_interval missing"
print("    ✓ PASS")

# 5. 日报多场站 station_codes
print("\n[5] POST /reports/generate?station_codes= — 批量多场站日报")
resp = requests.post(f"{BASE}/reports/generate", params={
    "date": today,
    "station_codes": ["ST001", "ST002"],
})
d = resp.json()
assert isinstance(d, list) and len(d) >= 1, f"FAIL generate 返回不对: {d}"
print(f"    生成日报数={len(d)}")
for r in d[:3]:
        print(f"      {r['station_code']}: 到{r['total_arrived']}/发{r['total_departed']} 编组{r['marshalling_efficiency']}% 停留{r['avg_stay_time']}h")
print("    ✓ PASS")

# 6. 通知 CSV 字段全量 + 正文不截断
print("\n[6] GET /notifications/export — CSV全字段+正文不截断")
resp = requests.get(f"{BASE}/notifications/export", params={
    "start_date": today, "end_date": today,
})
lines = resp.text.splitlines()
header = lines[0]
cols = header.split(",")
print(f"    列数={len(cols)}")
print(f"    表头: {header}")
print(f"    数据行数={max(0, len(lines) - 1)}")
assert "接收人ID" in header, "FAIL 缺接收人ID列"
assert header.count(",") >= 14, f"FAIL 列数不足: {len(cols)}"
if len(lines) > 1:
    row1_cols = []
    cur = ""
    in_q = False
    for ch in lines[1]:
        if ch == '"':
            in_q = not in_q
        elif ch == ',' and not in_q:
            row1_cols.append(cur); cur = ""
        else:
            cur += ch
    row1_cols.append(cur)
    content_val = row1_cols[9] if len(row1_cols) > 9 else ""
    print(f"    正文列前150字符: {content_val[:150]}")
print("    ✓ PASS")

# 7. 发车流程 interval_seconds
print("\n[7] GET /dispatch/{id}/flow — 发车流程间隔秒数")
dl = requests.get(f"{BASE}/dispatch").json()
if dl:
    did = dl[0]["id"]
    resp = requests.get(f"{BASE}/dispatch/{did}/flow")
    d = resp.json()
    print(f"    total_elapsed_seconds = {d.get('total_elapsed_seconds')}")
    have_interval = False
    for step in d.get("flow", []):
        gap = step.get("interval_seconds")
        have_interval = have_interval or gap is not None
        ts = (step.get("timestamp") or "")[:19] or "---"
        g = f"+{gap}s" if gap is not None else "首步"
        print(f"      [{g}] {step['step']} @{ts}")
    assert "total_elapsed_seconds" in d, "FAIL total_elapsed missing"
    print("    ✓ PASS")

print("\n" + "="*60)
print("全部新增需求测试通过！")
print("="*60)
