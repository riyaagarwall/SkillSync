from app import get_db

conn = get_db()
with conn, conn.cursor() as cur:
    cur.execute("DELETE FROM allocations WHERE id > 2")
    cur.execute("DELETE FROM timesheets WHERE id > 2")
    cur.execute("""
        UPDATE timesheets
        SET status = 'pending', reviewed_by = NULL, reviewed_at = NULL
        WHERE id = 2
    """)
conn.close()
print("Demo data reset.")