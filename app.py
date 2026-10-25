import os
from datetime import date, timedelta
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv(override=True)
app = Flask(__name__)
CORS(app)

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




MAX_WEEKLY_HOURS = 60  # business rule: change it if your company allows more


@app.route("/api/timesheets", methods=["POST"])
def submit_timesheet():
    data = request.get_json(silent=True) or {}

    try:
        allocation_id = int(data["allocation_id"])
        week_start = date.fromisoformat(data["week_start"])
        hours = float(data["hours"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="allocation_id, week_start (like 2026-11-09) and hours are required"), 400
    if week_start.weekday() != 0:
        return jsonify(error="week_start must be a Monday"), 400
    if not 0 <= hours <= MAX_WEEKLY_HOURS:
        return jsonify(error=f"hours must be between 0 and {MAX_WEEKLY_HOURS}"), 400

    conn = get_db()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, start_date, end_date FROM allocations WHERE id = %s",
                        (allocation_id,))
            alloc = cur.fetchone()
            if alloc is None:
                return jsonify(error="Allocation not found"), 404

            # The week (Monday to Sunday) must overlap the allocation dates
            week_end = week_start + timedelta(days=6)
            if week_start > alloc["end_date"] or week_end < alloc["start_date"]:
                return jsonify(error="That week is outside the allocation dates "
                                     f"({alloc['start_date']} to {alloc['end_date']})"), 400

            cur.execute("""
                SELECT id, status FROM timesheets
                WHERE allocation_id = %s AND week_start = %s FOR UPDATE
            """, (allocation_id, week_start))
            existing = cur.fetchone()

            if existing is None:
                cur.execute("""
                    INSERT INTO timesheets (allocation_id, week_start, hours)
                    VALUES (%s, %s, %s) RETURNING id
                """, (allocation_id, week_start, hours))
                return jsonify(id=cur.fetchone()["id"], status="pending", hours=hours), 201

            if existing["status"] == "rejected":
                # A rejected week can be corrected and sent for review again
                cur.execute("""
                    UPDATE timesheets
                    SET hours = %s, status = 'pending', reviewed_by = NULL, reviewed_at = NULL
                    WHERE id = %s
                """, (hours, existing["id"]))
                return jsonify(id=existing["id"], status="pending", hours=hours), 200

            return jsonify(error=f"A timesheet for that week already exists and is {existing['status']}"), 409
    finally:
        conn.close()


@app.route("/api/timesheets")
def list_timesheets():
    status = request.args.get("status")
    if status and status not in ("pending", "approved", "rejected"):
        return jsonify(error="status must be pending, approved or rejected"), 400

    return jsonify(query("""
        SELECT t.id, e.name AS employee, p.name AS project,
               t.week_start::text AS week_start, t.hours::float AS hours, t.status,
               r.name AS reviewed_by, t.reviewed_at::text AS reviewed_at
        FROM timesheets t
        JOIN allocations a ON a.id = t.allocation_id
        JOIN employees e ON e.id = a.employee_id
        JOIN projects p ON p.id = a.project_id
        LEFT JOIN employees r ON r.id = t.reviewed_by
        WHERE (%s::text IS NULL OR t.status = %s)
        ORDER BY t.week_start, e.name
    """, (status, status)))


@app.route("/api/timesheets/<int:timesheet_id>/review", methods=["POST"])
def review_timesheet(timesheet_id):
    data = request.get_json(silent=True) or {}
    decision = data.get("decision")
    try:
        reviewer_id = int(data["reviewer_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="reviewer_id is required"), 400
    if decision not in ("approved", "rejected"):
        return jsonify(error="decision must be 'approved' or 'rejected'"), 400

    conn = get_db()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT name, role FROM employees WHERE id = %s", (reviewer_id,))
            reviewer = cur.fetchone()
            if reviewer is None or reviewer["role"] not in ("pm", "admin"):
                return jsonify(error="Only a project manager or admin can review timesheets"), 403

            cur.execute("SELECT status FROM timesheets WHERE id = %s FOR UPDATE", (timesheet_id,))
            ts = cur.fetchone()
            if ts is None:
                return jsonify(error="Timesheet not found"), 404
            if ts["status"] != "pending":
                return jsonify(error=f"This timesheet is already {ts['status']}"), 409

            cur.execute("""
                UPDATE timesheets
                SET status = %s, reviewed_by = %s, reviewed_at = NOW()
                WHERE id = %s
            """, (decision, reviewer_id, timesheet_id))
    finally:
        conn.close()
    return jsonify(id=timesheet_id, status=decision, reviewed_by=reviewer["name"])

@app.route("/api/milestones", methods=["POST"])
def create_milestone():
    data = request.get_json(silent=True) or {}
    try:
        project_id = int(data["project_id"])
        title = str(data["title"]).strip()
        due = date.fromisoformat(data["due_date"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="project_id, title and due_date (like 2027-01-31) are required"), 400
    if not title:
        return jsonify(error="title cannot be empty"), 400

    proj = query("SELECT start_date, end_date FROM projects WHERE id = %s", (project_id,), one=True)
    if proj is None:
        return jsonify(error="Project not found"), 404
    if not proj["start_date"] <= due <= proj["end_date"]:
        return jsonify(error=f"due_date must be within the project dates "
                             f"({proj['start_date']} to {proj['end_date']})"), 400

    conn = get_db()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO milestones (project_id, title, due_date)
                VALUES (%s, %s, %s) RETURNING id
            """, (project_id, title, due))
            new_id = cur.fetchone()["id"]
    finally:
        conn.close()
    return jsonify(id=new_id, status="pending"), 201


@app.route("/api/milestones/<int:milestone_id>", methods=["PATCH"])
def update_milestone(milestone_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("pending", "in_progress", "done"):
        return jsonify(error="status must be pending, in_progress or done"), 400

    conn = get_db()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE milestones SET status = %s WHERE id = %s RETURNING id",
                        (status, milestone_id))
            if cur.fetchone() is None:
                return jsonify(error="Milestone not found"), 404
    finally:
        conn.close()
    return jsonify(id=milestone_id, status=status)


@app.route("/api/reports/availability")
def report_availability():
    as_of = request.args.get("as_of")
    if as_of:
        try:
            day = date.fromisoformat(as_of)
        except ValueError:
            return jsonify(error="as_of must look like 2026-12-01"), 400
        rows = query("SELECT * FROM availability_on(%s)", (day,))
    else:
        rows = query("SELECT * FROM v_employee_availability")
    return jsonify(as_of=as_of or str(date.today()), employees=rows)


@app.route("/api/reports/profitability")
def report_profitability():
    return jsonify(query("""
        SELECT project_id, project_name,
               approved_hours::float AS approved_hours,
               revenue::float AS revenue,
               cost::float AS cost,
               profit::float AS profit,
               margin_percent::float AS margin_percent
        FROM v_project_profitability
        ORDER BY project_name
    """))


@app.route("/api/reports/progress")
def report_progress():
    return jsonify(query("SELECT * FROM v_project_progress ORDER BY project_name"))


@app.route("/api/projects")
def list_projects():
    projects = query("""
        SELECT id, name, start_date::text AS start_date, end_date::text AS end_date,
               headcount, min_experience_years::float AS min_experience_years,
               billing_rate::float AS billing_rate
        FROM projects ORDER BY name
    """)
    reqs = query("""
        SELECT pr.project_id, s.name AS skill, pr.min_proficiency
        FROM project_requirements pr JOIN skills s ON s.id = pr.skill_id
        ORDER BY s.name
    """)
    for p in projects:
        p["requirements"] = [
            {"skill": r["skill"], "min_proficiency": r["min_proficiency"]}
            for r in reqs if r["project_id"] == p["id"]
        ]
    return jsonify(projects)
    
@app.route("/")
def home():
    return jsonify(name="SkillSync API", status="running", health="/api/health")

@app.after_request
def allow_private_network(response):
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

if __name__ == "__main__":
    app.run(debug=True)