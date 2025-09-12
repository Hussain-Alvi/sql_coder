# SQLCoder API with FastAPI + LangChain + Gemini + Gradio UI

This project is a **modular FastAPI application** that:
 
 - Generates SQL queries from natural language using **Google Gemini (via LangChain)**.
- Executes queries on **SQL Server** via `pyodbc`.
- Stores history and session memory in **MongoDB**.
- Provides a **Gradio UI** to test all endpoints without needing Postman.
- Supportive Python Verion 3.11.9 for running this app.
- Store your Gemini Generated API key in Config.py
  
Database Setup (SQL Server):

- This project connects to a SQL Server database using ODBC + pyodbc.
- Windows: Download SQL Server Management Studio.
- Windows: Install ODBC Driver 17
- You should have database file to load into your Microsoft SQL Server.
  
Configure Connection in config.py :

DB_CONFIG = {
    "driver": "{ODBC Driver 17 for SQL Server}",  # use the driver you installed
    "server": "localhost,1433",                   # hostname or IP of SQL Server
    "database": "YourDatabaseName",
    "uid": "",                    # SQL Server username
    "pwd": "",                    # SQL Server password
}
 ## 📂 Project Structure
