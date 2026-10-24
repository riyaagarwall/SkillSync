import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv(override=True)

path = sys.argv[1]
conn = psycopg2.connect(os.environ["DATABASE_URL"])

with conn, conn.cursor() as cur:
    with open(path, encoding="utf-8") as f:
        cur.execute(f.read())

    print(f"Ran {path}. Row counts:")
    for table in ["employees", "skills", "employee_skills", "certifications",
                  "projects", "project_requirements", "allocations", "timesheets"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table}: {cur.fetchone()[0]}")

conn.close()