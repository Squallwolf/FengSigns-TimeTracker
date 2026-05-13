#!/usr/bin/env python3
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL nicht gesetzt. Setze sie in .env oder als Umgebungsvariable.")
    exit(1)

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    pin TEXT UNIQUE NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    is_present BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS scans (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES employees(id) ON DELETE CASCADE,
    event_type TEXT CHECK (event_type IN ('IN', 'OUT')),
    scan_time TIMESTAMPTZ DEFAULT NOW()
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS idx_scans_emp_time ON scans(employee_id, scan_time DESC)")

conn.commit()
cur.close()
conn.close()
print("✅ Datenbank initialisiert")
