# api.py
from fastapi import FastAPI
from pydantic import BaseModel
import uuid
from typing import Optional

import config
from db_ops import (
    log_message_to_db,
    export_schema_to_file,
    read_schema_from_file,
    get_connection,
    history_collection
)
from llm_chains import generate_sql_query, generate_suggestions
from utils import normalize_input, looks_like_sql
from memory_store import session_memories, get_or_create_memory

# load initial schema context
DB_SCHEMA_CONTEXT = read_schema_from_file(config.SCHEMA_FILE)

class QueryRequest(BaseModel):
    user_input: str
    session_id: Optional[str] = None  # ✅ NEW: session ID

class SessionCreateResponse(BaseModel):
    session_id: str

app = FastAPI(
    title="SQLCoder API",
    description="Generate, Execute SQL queries and Export Schema from SQL Server.",
    version="0.5.0"
)


# Execute SQL (keeps original logic)
def execute_sql_query(sql_query: str, user_input: str = ""):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql_query)

        results = None

        # Iterate through all possible result sets
        while True:
            if cursor.description is not None:  # Found a result set
                columns = [column[0] for column in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                results = {"status_code": 200, "columns": columns, "rows": rows}
                break  # Stop after first valid result set
            if not cursor.nextset():
                break  # No more result sets

        if results is None:
            conn.commit()
            results = {"status_code": 200, "message": "Query executed successfully but Data not found.!"}

        cursor.close()
        conn.close()
        return results

    except Exception as e:
        # The original file had duplicated exception blocks; reproduce behavior but prefer friendly messages:
        error_msg = str(e).lower()

        if "invalid column name" in error_msg:
            friendly_error = "⚠️ The query refers to a column that does not exist in the specified table. Please check the column names."
        elif "invalid object name" in error_msg:
            friendly_error = "⚠️ The query refers to a table, view, or object that does not exist in the database. Please verify the name."
        elif "could not find stored procedure" in error_msg:
            friendly_error = "⚠️ The stored procedure you are trying to call does not exist. Ensure the name is correct and it's available."
        elif "syntax error" in error_msg or "incorrect syntax" in error_msg:
            friendly_error = "⚠️ There seems to be a syntax error in your SQL query. Please review the SQL for typos or structural mistakes."
        elif "permission denied" in error_msg or "access denied" in error_msg:
            friendly_error = "⚠️ You do not have the necessary permissions to perform this operation. Please contact your database administrator."
        elif "timeout" in error_msg:
            friendly_error = "⚠️ The query execution timed out. This might be due to a very large dataset or an inefficient query."
        elif "duplicate key" in error_msg or "primary key violation" in error_msg:
            friendly_error = "⚠️ You are trying to insert a duplicate value into a column that requires unique values (e.g., a primary key)."
        elif "conversion failed" in error_msg or "data type mismatch" in error_msg:
            friendly_error = "⚠️ Data type conversion failed. The query is trying to convert data to an incompatible type (e.g., text to number)."
        else:
            friendly_error = f"⚠️ SQL execution failed: {str(e)}"

        suggestions = generate_suggestions(friendly_error, user_input)
        log_message_to_db(sql_query, "", friendly_error, suggestions)
        return {"status_code": 400, "error_message": friendly_error, "suggestions": suggestions}


# ---------------- API ENDPOINT ----------------
@app.post("/generate-sql")
def generate_sql(request: QueryRequest):
    normalized_input = normalize_input(request.user_input)

    if not normalized_input:
        return {
            "status_code": 400,
            "error_message": "⚠️ Please give some input.!",
            "suggestions": "Example: 'Show all tables in the database' or 'List customers who purchased in 2023'."
        }

    prompt = f"User Input: {normalized_input}"
    # pass schema into chain by setting DB_SCHEMA_CONTEXT global or via chain run
    global DB_SCHEMA_CONTEXT
    response = generate_sql_query(prompt, request.session_id)
    # If SQL generator expects schema text, we must ensure it has been loaded in memory_store's LLM runs
    # To maintain behavior, set DB_SCHEMA_CONTEXT variable from file if empty
    
    if isinstance(response, bytes):
        response = response.decode("utf-8", errors="ignore")
    
    if not DB_SCHEMA_CONTEXT or "Schema not found" in DB_SCHEMA_CONTEXT:
        DB_SCHEMA_CONTEXT = read_schema_from_file()

    if looks_like_sql(response):
        execution_result = execute_sql_query(response, request.user_input)
        log_message_to_db(
            request.user_input,
            response,
            None if execution_result["status_code"] == 200 else execution_result.get("error"),
            execution_result.get("suggestions"),
            request.session_id
        )
        return {
            "status_code": 200,
            "generated_sql": response,
            "execution_result": execution_result
        }
    else:
        if not response.strip():
            response = "⚠️ This doesn’t look like a database query. Please try asking something related to SQL or databases."
        suggestions = generate_suggestions(response, request.user_input)
        log_message_to_db(request.user_input, "", response, suggestions, request.session_id)
        return {"status_code": 400, "error_message": response, "suggestions": suggestions}


# ---------------- NEW SESSION ENDPOINTS ----------------
@app.post("/sessions", response_model=SessionCreateResponse)
def create_session():
    new_session_id = str(uuid.uuid4())
    return {"session_id": new_session_id}


@app.get("/sessions")
def list_sessions():
    sessions = history_collection.distinct("session_id")
    return {"status_code": 200, "sessions": [s for s in sessions if s]}


@app.get("/sessions/{session_id}")
def get_session_history(session_id: str):
    logs = list(history_collection.find({"session_id": session_id}).sort("timestamp", 1))
    for log in logs:
        log["_id"] = str(log["_id"])
    return {"status_code": 200, "total_logs": len(logs), "history": logs}


# ---------------- DELETE SESSION ENDPOINTS ----------------
@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    result = history_collection.delete_many({"session_id": session_id})
    if result.deleted_count > 0:
        session_memories.pop(session_id, None)  # also clear runtime memory
        return {"status_code": 200, "message": f"Session {session_id} deleted.", "deleted_logs": result.deleted_count}
    return {"status_code": 404, "error_message": f"No logs found for session {session_id}."}


@app.delete("/sessions")
def delete_all_sessions():
    result = history_collection.delete_many({})
    session_memories.clear()  # clear runtime memory
    return {"status_code": 200, "message": "All sessions deleted.", "deleted_logs": result.deleted_count}


# ---------------- EXPORT-SCHEMA ENDPOINT ----------------
@app.get("/export-schema")
def export_schema():
    result = export_schema_to_file()
    # Update global DB_SCHEMA_CONTEXT if successful
    global DB_SCHEMA_CONTEXT
    if result.get("status_code") == 200 and "schema_lines" in result:
        DB_SCHEMA_CONTEXT = "\n".join(result["schema_lines"])
    return result


# ---------------- HISTORY ENDPOINT ----------------
@app.get("/history")
def get_history():
    logs = list(history_collection.find().sort("timestamp", -1))
    for log in logs:
        log["_id"] = str(log["_id"])  # convert ObjectId to string
    return {"status_code": 200, "total_logs": len(logs), "history": logs}
