import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv(override=True)
app = Flask(__name__)


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


if __name__ == "__main__":
    app.run(debug=True)