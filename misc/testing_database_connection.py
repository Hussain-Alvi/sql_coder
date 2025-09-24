import pyodbc

conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=HAMIDWORKPC;"
    "DATABASE=itsdrystock;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

try:
    cnxn = pyodbc.connect(conn_str, autocommit=True)
    cursor = cnxn.cursor()
    print("✅ Connection successful")

    # Test query: get top 5 tables from sys.tables
    cursor.execute("SELECT TOP 5 name FROM sys.tables;")
    for row in cursor.fetchall():
        print(row[0])

except Exception as e:
    print("❌ Connection failed:", e)
