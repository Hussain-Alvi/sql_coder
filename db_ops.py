# db_ops.py
import os
from datetime import datetime
import pyodbc
from pymongo import MongoClient
from typing import List
import config

# Mongo client
client = MongoClient(config.MONGO_URI)
db = client[config.MONGO_DB]
history_collection = db[config.MONGO_COLLECTION]

# ---------------- LOGGING ----------------
def log_message_to_db(user_input: str, response: str, error: str = None, suggestions: str = None,
                      session_id: str = None):
    entry = {
        "timestamp": datetime.now(),
        "session_id": session_id,
        "user_input": user_input,
        "response": response,
        "error": error,
        "suggestions": suggestions
    }
    history_collection.insert_one(entry)


def get_connection():
    conn_str = f"DRIVER={{{config.DB_CONFIG['driver']}}};SERVER={config.DB_CONFIG['server']};DATABASE={config.DB_CONFIG['database']};"
    if config.DB_CONFIG['uid']:
        conn_str += f"UID={config.DB_CONFIG['uid']};PWD={config.DB_CONFIG['pwd']};"
    else:
        conn_str += "Trusted_Connection=yes;"
    return pyodbc.connect(conn_str)


# ---------------- EXPORT SCHEMA ----------------
def export_schema_to_file(schema_file: str = config.SCHEMA_FILE):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
                       SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
                       FROM INFORMATION_SCHEMA.COLUMNS
                       ORDER BY TABLE_NAME;
                       """)
        schema_lines = [f"{row[0]} - {row[1]} ({row[2]})" for row in cursor.fetchall()]

        with open(schema_file, "w", encoding="utf-8") as f:
            f.write("\n".join(schema_lines))

        cursor.close()
        conn.close()
        return {"status_code": 200, "message": "Schema exported to databaseSchema.txt and loaded into context",
                "total_columns": len(schema_lines), "schema_lines": schema_lines}
    except Exception as e:
        return {"status_code": 500, "error_message": f"Schema export failed: {str(e)}"}


def read_schema_from_file(schema_file: str = config.SCHEMA_FILE) -> str:
    if os.path.exists(schema_file):
        with open(schema_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "⚠️ Schema not found. Please export schema first."
