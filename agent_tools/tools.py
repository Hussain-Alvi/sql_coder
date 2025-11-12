# tools/tools.py
import logging
import os
import pandas as pd
import pyodbc
from dynaconf import Dynaconf
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from langchain.tools import tool

# -------------------- TOOL 1 --------------------

class GetTableInfoInput(BaseModel):
    table_names: List[str] = Field(
        description="List of table names for which schema details (columns, data types, primary keys, foreign keys) are required."
    )

@tool("get_table_info", args_schema=GetTableInfoInput, return_direct=False)
def get_table_info(table_names: List[str]) -> str:
    """
    Use this tool to retrieve schema details of one or more database tables.
    The tool returns a CREATE TABLE DDL representation that includes columns,
    data types, primary keys, foreign keys, or M-schema if available.
    """
    pass


def load_m_schema_from_csv(csv_path: str, table_names: List[str], logger: logging.Logger):
    found_schemas = {}
    missing_tables = []

    try:
        logger.info(f"Loading M-schema CSV from: {csv_path}")
        df = pd.read_csv(csv_path, encoding="utf-8")
        if "Table_name" not in df.columns or "M_Schema" not in df.columns:
            raise ValueError("CSV must contain 'Table_name' and 'M_Schema' columns.")

        csv_map = {t.strip(): s for t, s in zip(df["Table_name"], df["M_Schema"])}

        for t in table_names:
            if t in csv_map:
                found_schemas[t] = csv_map[t]
                logger.info(f"✅ Found M-schema for table: {t}")
            else:
                missing_tables.append(t)
                logger.info(f"ℹ️ No M-schema found in CSV for table: {t}")

    except FileNotFoundError:
        logger.warning(f"⚠️ M-schema CSV file not found at path: {csv_path}")
        missing_tables = table_names
    except Exception as e:
        logger.error(f"Error loading M-schema CSV: {e}")
        missing_tables = table_names

    return found_schemas, missing_tables


def get_table_info_imp(settings: Dynaconf, logger: logging.Logger,
                       conn_str: str,
                       table_names: List[str]) -> str:

    if not table_names or len(table_names) == 0:
        return "❌ No table names provided."

    csv_path = settings.TABLE_DETAILS_CSV_PATH
    output = []

    csv_schemas, missing_tables = load_m_schema_from_csv(csv_path, table_names, logger)

    for table, schema in csv_schemas.items():
        output.append(f"🔹 M-Schema for {table}:\n{schema.strip()}")

    if not missing_tables:
        return "\n\n".join(output)

    try:
        cnxn = pyodbc.connect(conn_str, autocommit=False)
        cursor = cnxn.cursor()

        for table in missing_tables:
            cursor.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", table
            )
            if cursor.fetchone()[0] == 0:
                output.append(f"⚠️ Table '{table}' does not exist.")
                continue

            cursor.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
                """,
                table,
            )
            columns = cursor.fetchall()

            cursor.execute(
                """
                SELECT k.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS t
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
                ON t.CONSTRAINT_NAME = k.CONSTRAINT_NAME
                WHERE t.TABLE_NAME = ? AND t.CONSTRAINT_TYPE = 'PRIMARY KEY'
                """,
                table,
            )
            pk_cols = [row[0] for row in cursor.fetchall()]

            cursor.execute(
                """
                SELECT 
                    f.NAME AS FK_NAME,
                    COL_NAME(fc.parent_object_id,fc.parent_column_id) AS COLUMN_NAME,
                    OBJECT_NAME(f.referenced_object_id) AS REFERENCED_TABLE,
                    COL_NAME(fc.referenced_object_id,fc.referenced_column_id) AS REFERENCED_COLUMN
                FROM sys.foreign_keys AS f
                INNER JOIN sys.foreign_key_columns AS fc 
                    ON f.OBJECT_ID = fc.constraint_object_id
                WHERE f.parent_object_id = OBJECT_ID(?)
                """,
                table,
            )
            fk_data = cursor.fetchall()

            ddl_lines = []
            for col_name, data_type, is_nullable, char_len in columns:
                type_str = f"{data_type}({char_len})" if char_len and char_len > 0 and data_type in ["nvarchar", "varchar", "char"] else data_type
                null_str = "NULL" if is_nullable == "YES" else "NOT NULL"
                ddl_lines.append(f"    {col_name} {type_str} {null_str}")

            if pk_cols:
                ddl_lines.append(f"    PRIMARY KEY ({', '.join(pk_cols)})")

            for fk_name, col, ref_table, ref_col in fk_data:
                ddl_lines.append(f"    FOREIGN KEY ({col}) REFERENCES {ref_table}({ref_col})")

            ddl = f"TABLE {table} (\n" + ",\n".join(ddl_lines) + "\n);"
            output.append(ddl)

        return "\n\n".join(output)

    except Exception as e:
        logger.error(f"Error fetching table info: {e}")
        return f"❌ Failed to get schema info. Error: {e}"


# -------------------- TOOL 2 --------------------

class ExecuteSQLQueryInput(BaseModel):
    query: str = Field(description="The SQL query to be executed on the relational database.")
    limit: Optional[int] = Field(default=5, description="Maximum number of rows to return.")

@tool("execute_sql_query", args_schema=ExecuteSQLQueryInput, return_direct=False)
def execute_sql_query(query: str, limit: int = 5) -> str:
    """
    Executes an SQL query on the relational database and returns the results.
    The results are returned in a structured JSON format including column names and row values.
    """
    pass


def execute_sql_query_imp(settings: Dynaconf, logger: logging.Logger,
                          conn_str: str, query: str, limit: int = 5) -> Dict[str, Any]:

    try:
        if limit is None:
            limit = 20
        else:
            limit = min(limit, 20)

        if limit is not None and query.startswith('"') and query.endswith('"'):
            query = query[1:-1]

        cnxn = pyodbc.connect(conn_str, autocommit=False)
        cursor = cnxn.cursor()
        cursor.execute(query)

        if cursor.description is None:
            return {"status": "success", "message": "✅ Query executed successfully. No rows returned.", "rows_returned": 0, "data": []}

        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        total_rows = len(rows)
        clipped = total_rows > limit
        rows = rows[:limit]

        data = [dict(zip(columns, row)) for row in rows]

        result = {"status": "success", "message": "✅ Query executed successfully.", "rows_returned": total_rows, "data": data}

        if clipped:
            result["note"] = f"⚠️ {total_rows} rows received. Showing first {limit} rows only."

        return result

    except Exception as e:
        logger.error(f"SQL Execution Error: {e}")
        return {"status": "error", "message": f"❌ Query failed with error: {str(e)}", "rows_returned": 0, "data": []}
