import json
from app import app

client = app.test_client()

tests = {
    "Test 1: Python level 4+, 3 people": {
        "requirements": [{"skill": "Python", "min_proficiency": 4}],
        "min_experience_years": 3,
        "headcount": 3,
        "start_date": "2026-11-01",
        "end_date": "2027-03-31",
    },
    "Test 2: Retail Analytics Platform needs": {
        "requirements": [
            {"skill": "Python", "min_proficiency": 3},
            {"skill": "SQL", "min_proficiency": 3},
            {"skill": "Data Visualization", "min_proficiency": 3},
        ],
        "min_experience_years": 3,
        "headcount": 3,
        "start_date": "2026-11-01",
        "end_date": "2027-03-31",
    },
}

for title, payload in tests.items():
    resp = client.post("/api/team-builder", json=payload)
    result = resp.get_json()
    print("=" * 60)
    print(title, "| status:", resp.status_code)
    print("found:", result.get("found"), "| shortfall:", result.get("shortfall"))
    for person in result.get("team", []):
        print(f"  {person['name']}: score {person['score']}, free {person['available_percent']}%")
    for person in result.get("excluded", []):
        print(f"  left out - {person['name']}: {'; '.join(person['reasons'])}")