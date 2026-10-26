# SkillSync: HR Resource Allocation Portal

A backend for an internal HR-tech portal that helps a company staff its projects. It stores each
employee's skills, proficiency scores (0 to 5), experience and certifications, then uses that data
to match people to new projects. It replaces manual, spreadsheet-based resourcing.

**Stack:** Python, Flask, PostgreSQL, SQL (views and functions), psycopg2


## Screenshots
The interface is React, generated with Lovable from this API. The backend, database design, matching logic and tests are my own.

### Staarting Page (How the company's HR open to portal)
![Team builder](screenshots/main-page.png)

### Team builder (ranked matches and why others were left out)
![Team builder](screenshots/team-builder.png)

### Employees and team skill radar
![Employees](screenshots/employees.png)

### Allocations and timesheet approvals
![Timesheets](screenshots/timesheets.png)

### Reports
![Availability](screenshots/reports-availability.png)
![Profitability](screenshots/reports-profitability.png)

## What it does
- **Skill profiles:** employees, skills, proficiency levels and certifications, served as JSON.
- **Team builder:** a project manager sends the skills, minimum levels, experience, headcount and
  dates a project needs. The engine filters out anyone underqualified or fully booked, ranks the
  rest with a weighted score (skills 60%, experience 15%, availability 25%), and explains why each
  excluded person was left out.
- **Allocation:** locks employees to projects with double-booking checks. It looks at the real peak
  workload across overlapping dates, and uses a row lock so two simultaneous requests cannot both
  book the same person past 100%.
- **Timesheets:** employees log weekly hours (Mondays only, within their allocation dates). Only a
  PM or admin can approve or reject, and a rejected week can be corrected and resubmitted.
- **Progress and reports:** milestone tracking, plus availability, profitability and project
  progress reports built from SQL views. Profit counts approved timesheets only.

## API
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Check the database connection |
| GET | `/api/skills` | List skills |
| GET | `/api/employees` | List employees with their skills |
| GET | `/api/employees/<id>` | One employee with skills and certifications |
| POST | `/api/team-builder` | Rank the best-fit available employees for a project |
| GET / POST | `/api/allocations` | List or create allocations (double-booking checked) |
| DELETE | `/api/allocations/<id>` | Remove an allocation |
| GET / POST | `/api/timesheets` | List (filter with `?status=pending`) or submit hours |
| POST | `/api/timesheets/<id>/review` | PM approves or rejects |
| POST | `/api/milestones` | Add a milestone |
| PATCH | `/api/milestones/<id>` | Update a milestone's status |
| GET | `/api/reports/availability` | Who is free, optionally `?as_of=2026-12-01` |
| GET | `/api/reports/profitability` | Revenue, cost and margin per project |
| GET | `/api/reports/progress` | Milestone completion per project |
| GET | `/api/projects` | List projects with their required skills |

### Example: find a team
```
POST /api/team-builder
{
  "requirements": [{"skill": "Python", "min_proficiency": 4}],
  "min_experience_years": 3,
  "headcount": 3,
  "start_date": "2026-11-01",
  "end_date": "2027-03-31"
}
```

## Database
Eight tables (`employees`, `skills`, `employee_skills`, `certifications`, `projects`,
`project_requirements`, `allocations`, `timesheets`) plus `milestones`, with `CHECK` and foreign-key
constraints. Reports use the views `v_employee_availability`, `v_project_profitability` and
`v_project_progress`, and the function `availability_on(date)`.

## Run it locally
1. Install PostgreSQL and create a database named `skillsync`.
2. Create a `.env` file: `DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@127.0.0.1:5432/skillsync`
3. Install and set up:
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python apply_schema.py
python run_sql.py migration_001.sql
python run_sql.py seed.sql
python run_sql.py migration_002.sql
python app.py
```
4. Open `http://127.0.0.1:5000/api/health`.

## Tests
Each script prints PASS or FAIL for every check and cleans up the data it creates:
```
python test_team_builder.py
python test_allocations.py
python test_timesheets.py
python test_reports.py
```

## Known limitations
- No login yet: `reviewer_id` is sent in the request, so a real version would identify the person
  through authentication.
- No frontend yet.
- The team-builder score weights are a starting point and can be tuned.
- Sample data is fictional.