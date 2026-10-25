from app import app, get_db

client = app.test_client()


def expect(label, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")


# ---- Availability ----
r = client.get("/api/reports/availability?as_of=2026-12-01").get_json()
people = {e["emp_name"]: e for e in r["employees"]}
expect("9 employees listed (the PM is excluded)", len(people) == 9)
expect("Isha is fully booked (0% free)", people["Isha Verma"]["available_percent"] == 0)
expect("Rohan has 40% free", people["Rohan Iyer"]["available_percent"] == 40)
expect("Aarav is 100% free", people["Aarav Mehta"]["available_percent"] == 100)

r = client.get("/api/reports/availability?as_of=2030-01-01").get_json()
expect("Everyone is free after the projects end",
       all(e["available_percent"] == 100 for e in r["employees"]))
expect("Today's view returns 9 employees",
       len(client.get("/api/reports/availability").get_json()["employees"]) == 9)
expect("Bad date gives 400", client.get("/api/reports/availability?as_of=oops").status_code == 400)

# ---- Profitability (only the approved 40h from the sample data counts) ----
rows = {p["project_name"]: p for p in client.get("/api/reports/profitability").get_json()}
p1 = rows["Retail Analytics Platform"]
expect("Project 1: 40 approved hours", p1["approved_hours"] == 40)
expect("Project 1: revenue 4800 (40h x 120)", p1["revenue"] == 4800)
expect("Project 1: cost 2600 (40h x 65)", p1["cost"] == 2600)
expect("Project 1: profit 2200, margin 45.8%", p1["profit"] == 2200 and p1["margin_percent"] == 45.8)
expect("Project 2: no approved hours, no margin yet",
       rows["Customer Support Chatbot"]["approved_hours"] == 0
       and rows["Customer Support Chatbot"]["margin_percent"] is None)


# ---- Milestones and progress ----
def progress(name):
    data = client.get("/api/reports/progress").get_json()
    return next(p for p in data if p["project_name"] == name)


start = progress("Retail Analytics Platform")
expect("Project 1: 1 of 4 milestones done = 25%",
       start["total_milestones"] == 4 and start["done_milestones"] == 1
       and start["percent_complete"] == 25)

new_id = None
try:
    resp = client.post("/api/milestones",
                       json={"project_id": 2, "title": "Test milestone", "due_date": "2027-01-15"})
    new_id = resp.get_json().get("id")
    expect("Create a milestone", resp.status_code == 201)
    expect("Due date outside the project is rejected", client.post(
        "/api/milestones",
        json={"project_id": 2, "title": "Too late", "due_date": "2028-01-01"}).status_code == 400)
    expect("Unknown project is rejected", client.post(
        "/api/milestones",
        json={"project_id": 99, "title": "x", "due_date": "2027-01-15"}).status_code == 404)

    patch = f"/api/milestones/{new_id}"
    expect("Bad status is rejected", client.patch(patch, json={"status": "finished"}).status_code == 400)
    expect("Mark it done", client.patch(patch, json={"status": "done"}).status_code == 200)

    p2 = progress("Customer Support Chatbot")
    expect("Project 2: 1 of 3 done = 33%",
           p2["total_milestones"] == 3 and p2["done_milestones"] == 1 and p2["percent_complete"] == 33)
finally:
    if new_id:
        conn = get_db()
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM milestones WHERE id = %s", (new_id,))
        conn.close()
        print("Cleaned up the test milestone.")