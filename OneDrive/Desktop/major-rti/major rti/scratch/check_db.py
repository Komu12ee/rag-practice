import sqlite3
import json
from pathlib import Path

db_path = Path("c:/Users/hp/projects/rti-project/offline/rti/backend/rti_audit.db")

print("DB Path exists:", db_path.exists())

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Get table info
cursor.execute("PRAGMA table_info(audit_trail)")
columns = cursor.fetchall()
print("\n--- Columns in audit_trail ---")
for col in columns:
    print(col)

# Get row count
cursor.execute("SELECT COUNT(*) FROM audit_trail")
count = cursor.fetchone()[0]
print("\nRow count:", count)

# Get last 5 records
cursor.execute("SELECT audit_id, timestamp, pio_action_taken, current_hash FROM audit_trail ORDER BY timestamp DESC LIMIT 5")
rows = cursor.fetchall()
print("\n--- Last 5 records ---")
for row in rows:
    print(row)

# Let's inspect if any exceptions occur when we attempt a dry-run insert of a dummy record
try:
    cursor.execute("SELECT * FROM audit_trail LIMIT 1")
    one = cursor.fetchone()
    print("\n--- Sample row data keys ---")
    if one:
        names = [description[0] for description in cursor.description]
        for name, val in zip(names, one):
            print(f"{name}: {type(val)} = {repr(val)[:100]}")
except Exception as e:
    print("Error reading sample row:", e)

conn.close()
