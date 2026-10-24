import os
from datetime import date

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv(override=True)
app = Flask(__name__)

# How much each factor counts towards the ranking score (must add up to 1.0)
WEIGHTS = {"skills": 0.60, "experience": 0.15, "availability": 0.25}


def get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)


def query(sql, params=None, one=False):
    """Run a SELECT and return the rows (or one row)."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone() if one else cur.fetchall()
    finally:
        conn.close()


@app.route("/api/health")
def health():
    row = query("SELECT NOW() AS now", one=True)
    return jsonify(status="ok", time=str(row["now"]))


@app.route("/api/skills")
def list_skills():
    return jsonify(query("SELECT id, name FROM skills ORDER BY name"))


@app.route("/api/employees")
def list_employees():
    rows = query("""
        SELECT e.id, e.name, e.email, e.role,
               e.experience_years::float AS experience_years,
               COALESCE(
                   json_agg(
                       json_build_object('skill', s.name, 'proficiency', es.proficiency)
                       ORDER BY es.proficiency DESC
                   ) FILTER (WHERE s.id IS NOT NULL),
                   '[]'
               ) AS skills
        FROM employees e
        LEFT JOIN employee_skills es ON es.employee_id = e.id
        LEFT JOIN skills s ON s.id = es.skill_id
        GROUP BY e.id
        ORDER BY e.name
    """)
    return jsonify(rows)


@app.route("/api/employees/<int:employee_id>")
def get_employee(employee_id):
    emp = query("""
        SELECT id, name, email, role,
               experience_years::float AS experience_years,
               hourly_cost::float AS hourly_cost
        FROM employees WHERE id = %s
    """, (employee_id,), one=True)
    if emp is None:
        return jsonify(error="Employee not found"), 404

    emp["skills"] = query("""
        SELECT s.name AS skill, es.proficiency
        FROM employee_skills es JOIN skills s ON s.id = es.skill_id
        WHERE es.employee_id = %s
        ORDER BY es.proficiency DESC, s.name
    """, (employee_id,))

    emp["certifications"] = query("""
        SELECT name, issued_on::text AS issued_on
        FROM certifications WHERE employee_id = %s ORDER BY issued_on DESC
    """, (employee_id,))

    return jsonify(emp)


@app.route("/api/team-builder", methods=["POST"])
def team_builder():
    data = request.get_json(silent=True) or {}

    # ---- 1. Read and validate what the project needs ----
    try:
        start = date.fromisoformat(data.get("start_date", ""))
        end = date.fromisoformat(data.get("end_date", ""))
    except (TypeError, ValueError):
        return jsonify(error="start_date and end_date must look like 2026-11-01"), 400
    if end < start:
        return jsonify(error="end_date cannot be before start_date"), 400

    try:
        headcount = int(data.get("headcount", 1))
        min_exp = float(data.get("min_experience_years", 0))
        needs = {r["skill"]: int(r["min_proficiency"]) for r in data.get("requirements", [])}
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Each requirement needs a 'skill' and a numeric 'min_proficiency'"), 400

    if not needs:
        return jsonify(error="Add at least one required skill"), 400
    if headcount < 1 or any(not 1 <= m <= 5 for m in needs.values()):
        return jsonify(error="headcount must be at least 1 and min_proficiency between 1 and 5"), 400

    known = {row["name"] for row in query("SELECT name FROM skills")}
    unknown = [s for s in needs if s not in known]
    if unknown:
        return jsonify(error=f"Unknown skills: {', '.join(unknown)}"), 400

    # ---- 2. Get every employee with their skills and how booked they are ----
    # An allocation overlaps the project if it starts before the project ends
    # and ends after the project starts.
    employees = query("""
        SELECT e.id, e.name,
               e.experience_years::float AS experience_years,
               COALESCE((SELECT json_object_agg(s.name, es.proficiency)
                         FROM employee_skills es JOIN skills s ON s.id = es.skill_id
                         WHERE es.employee_id = e.id), '{}'::json) AS skills,
               COALESCE((SELECT SUM(a.percent_allocated)
                         FROM allocations a
                         WHERE a.employee_id = e.id
                           AND a.start_date <= %s AND a.end_date >= %s), 0)::int AS booked_percent
        FROM employees e
        WHERE e.role = 'employee'
        ORDER BY e.name
    """, (end, start))

    # ---- 3. Filter, then score ----
    qualified, excluded = [], []
    for emp in employees:
        reasons = []

        for skill, minimum in needs.items():
            have = emp["skills"].get(skill, 0)
            if have == 0:
                reasons.append(f"missing {skill}")
            elif have < minimum:
                reasons.append(f"{skill} level {have} is below the required {minimum}")

        if emp["experience_years"] < min_exp:
            reasons.append(f"{emp['experience_years']} years of experience is below the required {min_exp}")

        available = 100 - emp["booked_percent"]
        if available <= 0:
            reasons.append("fully booked during these dates")

        if reasons:
            excluded.append({"id": emp["id"], "name": emp["name"], "reasons": reasons})
            continue

        skill_score = sum(min(emp["skills"][s], 5) / 5 for s in needs) / len(needs)
        exp_score = min(emp["experience_years"] / 10, 1)
        avail_score = available / 100
        score = round(100 * (WEIGHTS["skills"] * skill_score
                             + WEIGHTS["experience"] * exp_score
                             + WEIGHTS["availability"] * avail_score), 1)

        qualified.append({
            "id": emp["id"],
            "name": emp["name"],
            "score": score,
            "experience_years": emp["experience_years"],
            "available_percent": available,
            "skill_levels": {s: emp["skills"][s] for s in needs},
        })

    # Best score first; if tied, the more experienced person goes first
    qualified.sort(key=lambda c: (-c["score"], -c["experience_years"]))
    team = qualified[:headcount]

    return jsonify(
        requested_headcount=headcount,
        found=len(team),
        shortfall=max(headcount - len(team), 0),
        team=team,
        other_qualified=qualified[headcount:],
        excluded=excluded,
    )




@app.route("/api/allocations", methods=["POST"])
def create_allocation():
    data = request.get_json(silent=True) or {}

    try:
        employee_id = int(data["employee_id"])
        project_id = int(data["project_id"])
        percent = int(data["percent_allocated"])
        start = date.fromisoformat(data["start_date"])
        end = date.fromisoformat(data["end_date"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="employee_id, project_id, percent_allocated, start_date and "
                             "end_date are required (dates look like 2026-11-01)"), 400
    if not 1 <= percent <= 100:
        return jsonify(error="percent_allocated must be between 1 and 100"), 400
    if end < start:
        return jsonify(error="end_date cannot be before start_date"), 400

    conn = get_db()
    try:
        with conn:  # commits if everything works, rolls back if anything fails
            with conn.cursor() as cur:
                # Lock this employee's row so two requests at the same moment
                # cannot both pass the check and double-book them.
                cur.execute("SELECT id, name, role FROM employees WHERE id = %s FOR UPDATE",
                            (employee_id,))
                emp = cur.fetchone()
                if emp is None:
                    return jsonify(error="Employee not found"), 404
                if emp["role"] != "employee":
                    return jsonify(error="Only employees can be allocated to projects"), 400

                cur.execute("SELECT id, name, start_date, end_date FROM projects WHERE id = %s",
                            (project_id,))
                proj = cur.fetchone()
                if proj is None:
                    return jsonify(error="Project not found"), 404
                if start < proj["start_date"] or end > proj["end_date"]:
                    return jsonify(error=f"Allocation must stay within the project dates "
                                         f"({proj['start_date']} to {proj['end_date']})"), 400

                # Existing allocations that overlap the requested dates
                cur.execute("""
                    SELECT percent_allocated, start_date, end_date
                    FROM allocations
                    WHERE employee_id = %s AND start_date <= %s AND end_date >= %s
                """, (employee_id, end, start))
                existing = cur.fetchall()

                # Workload only goes up on the day an allocation starts, so it is
                # enough to check the first day and each start date inside the window.
                check_days = {start} | {a["start_date"] for a in existing if a["start_date"] > start}
                peak = max(
                    sum(a["percent_allocated"] for a in existing
                        if a["start_date"] <= day <= a["end_date"])
                    for day in check_days
                )
                if peak + percent > 100:
                    return jsonify(
                        error=f"{emp['name']} would be over 100% booked",
                        current_peak_percent=peak,
                        requested_percent=percent,
                    ), 409

                cur.execute("""
                    INSERT INTO allocations
                        (employee_id, project_id, start_date, end_date, percent_allocated)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                """, (employee_id, project_id, start, end, percent))
                new_id = cur.fetchone()["id"]
    finally:
        conn.close()

    return jsonify(id=new_id, employee=emp["name"], project=proj["name"],
                   percent_allocated=percent, peak_after=peak + percent), 201


@app.route("/api/allocations")
def list_allocations():
    return jsonify(query("""
        SELECT a.id, e.name AS employee, p.name AS project,
               a.start_date::text AS start_date, a.end_date::text AS end_date,
               a.percent_allocated
        FROM allocations a
        JOIN employees e ON e.id = a.employee_id
        JOIN projects p ON p.id = a.project_id
        ORDER BY p.name, e.name
    """))


@app.route("/api/allocations/<int:allocation_id>", methods=["DELETE"])
def delete_allocation(allocation_id):
    conn = get_db()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM allocations WHERE id = %s RETURNING id", (allocation_id,))
            if cur.fetchone() is None:
                return jsonify(error="Allocation not found"), 404
    finally:
        conn.close()
    return jsonify(deleted=allocation_id)


if __name__ == "__main__":
    app.run(debug=True)