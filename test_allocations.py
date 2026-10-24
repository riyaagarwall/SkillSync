from app import app

client = app.test_client()
created = []


def book(label, expect, **body):
    resp = client.post("/api/allocations", json=body)
    result = resp.get_json()
    ok = "PASS" if resp.status_code == expect else "FAIL"
    print(f"[{ok}] {label} -> {resp.status_code}: {result.get('error') or result.get('employee')}")
    if resp.status_code == 201:
        created.append(result["id"])


P1 = dict(project_id=1, start_date="2026-11-01", end_date="2027-03-31")
P2 = dict(project_id=2, start_date="2026-11-15", end_date="2027-02-28")

try:
    # Aarav (id 1) is free: 60% works, then another 50% overlapping is too much
    book("Aarav 60% on project 2", 201, employee_id=1, percent_allocated=60, **P2)
    book("Aarav +50% overlapping (60+50 > 100)", 409, employee_id=1, percent_allocated=50,
         project_id=1, start_date="2026-12-01", end_date="2027-01-31")

    # Isha (id 8) is already at 100%
    book("Isha +10% (already 100%)", 409, employee_id=8, percent_allocated=10, **P2)

    # Rohan (id 3) is at 60%: exactly 40% more is fine, 1% more is not
    book("Rohan +40% (60+40 = 100)", 201, employee_id=3, percent_allocated=40, **P2)
    book("Rohan +1% (over 100)", 409, employee_id=3, percent_allocated=1, **P2)

    # Diya (id 2): two back-to-back 60% jobs never overlap each other,
    # so a 40% job across both periods is fine (peak is 60, not 120)
    book("Diya 60% Nov-Dec", 201, employee_id=2, percent_allocated=60,
         project_id=1, start_date="2026-11-01", end_date="2026-12-31")
    book("Diya 60% Jan-Feb", 201, employee_id=2, percent_allocated=60,
         project_id=1, start_date="2027-01-01", end_date="2027-02-28")
    book("Diya +40% across both (peak 60+40 = 100)", 201, employee_id=2, percent_allocated=40,
         project_id=1, start_date="2026-11-01", end_date="2027-02-28")

    # Bad input
    book("Bad percent (150)", 400, employee_id=1, percent_allocated=150, **P2)
    book("Dates outside the project", 400, employee_id=1, percent_allocated=10,
         project_id=2, start_date="2026-10-01", end_date="2027-02-28")
    book("Unknown employee", 404, employee_id=999, percent_allocated=10, **P2)
    book("PM cannot be allocated", 400, employee_id=9, percent_allocated=10, **P2)
finally:
    for allocation_id in created:
        client.delete(f"/api/allocations/{allocation_id}")
    print(f"Cleaned up {len(created)} test allocations.")