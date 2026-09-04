import sqlite3
from pathlib import Path

def check():
    conn = sqlite3.connect("legal_metrology.db")
    c = conn.cursor()
    c.execute("SELECT count(1) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT count(1) FROM inspections")
    inspections = c.fetchone()[0]
    c.execute("SELECT count(1) FROM reports")
    reports = c.fetchone()[0]
    c.execute("SELECT id, inspection_number, location, notes, created_at FROM inspections")
    rows = c.fetchall()
    print(f"Users: {users}, Inspections: {inspections}, Reports: {reports}")
    for r in rows:
        print("Inspection:", r)
    conn.close()

if __name__ == "__main__":
    check()
