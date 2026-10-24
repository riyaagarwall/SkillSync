import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(override=True)

conn = psycopg2.connect(os.environ["DATABASE_URL"])
with open("schema.sql", encoding="utf-8") as f:
    sql = f.read()

with conn, conn.cursor() as cur:
    cur.execute(sql)
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name"
    )
    print("Tables created:", [row[0] for row in cur.fetchall()])

conn.close()