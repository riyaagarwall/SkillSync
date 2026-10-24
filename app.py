import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv(override=True)
app = Flask(__name__)


def get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)


@app.route("/api/health")
def health():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT NOW() AS now")
            row = cur.fetchone()
        return jsonify(status="ok", time=str(row["now"]))
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(debug=True)