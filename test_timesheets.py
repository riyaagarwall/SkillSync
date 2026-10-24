from app import app, get_db

client = app.test_client()
created = []


def check(label, expect, resp):
    result = resp.get_json()
    ok = "PASS" if resp.status_code == expect else "FAIL"
    if isinstance(result, list):
        detail = f"{len(result)} rows"
    else:
        detail = result.get("error") or result.get("status")
    print(f"[{ok}] {label} -> {resp.status_code}: {detail}")
    return result


W = dict(allocation_id=2, week_start="2026-11-09", hours=24)  # allocation 2 = Rohan

try:
    r = check("Submit 24h for the week of 9 Nov", 201, client.post("/api/timesheets", json=W))
    ts = r.get("id")
    if ts:
        created.append(ts)

    check("Same week again (already pending)", 409, client.post("/api/timesheets", json=W))
    check("week_start is not a Monday", 400,
          client.post("/api/timesheets", json={**W, "week_start": "2026-11-10"}))
    check("Week before the allocation starts", 400,
          client.post("/api/timesheets", json={**W, "week_start": "2026-10-05"}))
    check("100 hours in one week", 400, client.post("/api/timesheets", json={**W, "hours": 100}))
    check("Unknown allocation", 404,
          client.post("/api/timesheets", json={**W, "allocation_id": 999}))

    review = f"/api/timesheets/{ts}/review"
    check("A normal employee tries to approve", 403,
          client.post(review, json={"reviewer_id": 1, "decision": "approved"}))
    check("Invalid decision", 400,
          client.post(review, json={"reviewer_id": 9, "decision": "maybe"}))
    check("PM rejects it", 200, client.post(review, json={"reviewer_id": 9, "decision": "rejected"}))
    check("Review the same timesheet again", 409,
          client.post(review, json={"reviewer_id": 9, "decision": "approved"}))
    check("Resubmit the rejected week with 20h", 200,
          client.post("/api/timesheets", json={**W, "hours": 20}))
    check("PM approves it", 200, client.post(review, json={"reviewer_id": 9, "decision": "approved"}))
    check("Resubmit an approved week", 409, client.post("/api/timesheets", json=W))
    check("List pending timesheets", 200, client.get("/api/timesheets?status=pending"))
    check("Bad status filter", 400, client.get("/api/timesheets?status=nope"))
finally:
    conn = get_db()
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM timesheets WHERE id = ANY(%s)", (created,))
    conn.close()
    print(f"Cleaned up {len(created)} test timesheet(s).")