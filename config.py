# config.py
import os

# ---------------- GEMINI CONFIG ----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "Your Gemini API Key here.")

# ---------------- MONGODB CONFIG ----------------
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "sqlcoder_db"
MONGO_COLLECTION = "history"

# ---------------- DB CONFIG ----------------
DB_CONFIG = {
    "driver": "ODBC Driver 17 for SQL Server",
    "server": "DESKTOP-GMGNG7C",
    "database": "itsdrystock",
    "uid": "",
    "pwd": ""
}

# Schema filename used by export/load functions
SCHEMA_FILE = "databaseSchema.txt"
