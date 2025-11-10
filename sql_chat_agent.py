"""
Langchain agent of SQL Assistant.
"""
import logging
import os
import time
from datetime import date

import pandas as pd
import pyodbc
from dynaconf import Dynaconf
from typing import Optional, Dict, Any, List
# from langchain.agents.format_scratchpad import format_to_tool_messages
from langchain.agents.output_parsers.tools import ToolAgentAction, parse_ai_message_to_tool_action
from langchain_groq import ChatGroq
from langchain.tools import tool

# from langchain.agents import AgentExecutor
from langchain_core.agents import AgentFinish
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents.format_scratchpad.openai_tools import (format_to_openai_tool_messages)
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from pydantic import BaseModel, Field

from data_models import MessagesList, Message, Sender

today = date.today()
current_date = today.isoformat()

TABLE_LIST = [
    "Products",
    "SupplierProducts",
    "PurchaseOrderlines",
    "PurchaseOrders",
    "Suppliers",
    "ProductSales",
    "TillTransactionHeaders",
    "TillTransactionDetails",
    "Barcodes",
    "PromotionPrices",
    "PromotionCosts",
    "Prices",
    "CostpricesHistory",
    "StockTransactions",
    "Prices_Current",
    "CostPrices_Current",
    "BranchProducts",
    "CostPrices",
    "Departments",
    "SubDepartments",
    "PromotionCostPrice",
    "BranchPromotions",
    "MMHeaders",
    "MMDetails",
    "MMBranchHeaders",
    "PurchaseOrderLines",
    "Branches",
    "Pricebands",
    "Vatrates",
    "PromotionEvents",
]


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
    """
    Load m-schemas for given table names from a CSV file.
    Returns: (found_schemas: dict, missing_tables: list)
    """
    found_schemas = {}
    missing_tables = []

    try:
        logger.info(f"Loading M-schema CSV from: {csv_path}")
        df = pd.read_csv(csv_path, encoding="utf-8")
        if "Table_name" not in df.columns or "M_Schema" not in df.columns:
            raise ValueError("CSV must contain 'Table' and 'M_Schema' columns.")

        # Build a lookup dict
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
        missing_tables = table_names  # fallback to DB for all
    except Exception as e:
        logger.error(f"Error loading M-schema CSV: {e}")
        missing_tables = table_names  # fallback to DB for all

    return found_schemas, missing_tables


def get_table_info_imp(settings: Dynaconf, logger: logging.Logger,conn_str: str,
                       table_names: List[str]
                       ) -> str:
    """
    Retrieve schema details for given table(s) from M-schema CSV (if available),
    otherwise from SQL Server database.
    Returns combined CREATE TABLE DDL + M-schema text.
    """

    if not table_names or len(table_names) == 0:
        return "❌ No table names provided."

    csv_path = settings.TABLE_DETAILS_CSV_PATH
    output = []

    # --- Step 1: Load from CSV first
    csv_schemas, missing_tables = load_m_schema_from_csv(csv_path, table_names, logger)
    for table, schema in csv_schemas.items():
        output.append(f"🔹 M-Schema for {table}:\n{schema.strip()}")

    # --- Step 2: If all found in CSV, return immediately
    if not missing_tables:
        logger.info("All requested tables were found in M-schema CSV.")
        return "\n\n".join(output)

    # --- Step 3: Fallback to database for remaining tables
    try:
        cnxn = pyodbc.connect(conn_str, autocommit=False)
        cursor = cnxn.cursor()

        for table in missing_tables:
            # Check if table exists
            cursor.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", table
            )
            if cursor.fetchone()[0] == 0:
                output.append(f"⚠️ Table '{table}' does not exist.")
                continue

            # Get columns
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

            # Get primary keys
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

            # Get foreign keys
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

            # Build CREATE TABLE DDL
            ddl_lines = []
            for col in columns:
                col_name, data_type, is_nullable, char_len = col
                type_str = (
                    f"{data_type}({char_len})"
                    if char_len and char_len > 0 and data_type in ["nvarchar", "varchar", "char"]
                    else data_type
                )
                null_str = "NULL" if is_nullable == "YES" else "NOT NULL"
                ddl_lines.append(f"    {col_name} {type_str} {null_str}")

            if pk_cols:
                ddl_lines.append(f"    PRIMARY KEY ({', '.join(pk_cols)})")

            for fk in fk_data:
                fk_name, col, ref_table, ref_col = fk
                ddl_lines.append(f"    FOREIGN KEY ({col}) REFERENCES {ref_table}({ref_col})")

            ddl = f"TABLE {table} (\n" + ",\n".join(ddl_lines) + "\n);"
            output.append(ddl)

        return "\n\n".join(output)

    except Exception as e:
        logger.error(f"Error fetching table info: {e}")
        return f"❌ Failed to get schema info. Error: {e}"


class ExecuteSQLQueryInput(BaseModel):
    query: str = Field(description="The SQL query to be executed on the relational database.")
    limit: Optional[int] = Field(
        default=5,
        description="Maximum number of rows to return from the result set."
    )


@tool("execute_sql_query", args_schema=ExecuteSQLQueryInput, return_direct=False)
def execute_sql_query(query: str, limit: int = 5) -> str:
    """
    Executes an SQL query on the relational database and returns the results.
    The results are returned in a structured JSON format including column names and row values.
    """
    pass


def execute_sql_query_imp(settings: Dynaconf, logger: logging.Logger,
                          conn_str: str,
                          query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Execute an SQL query and return structured results.
    - If query fails: return structured error.
    - If results exceed `limit`: return only first `limit` rows and note clipping.
    """

    try:
        if limit is None:
            limit = 20  # default cap if not provided
        else:
            limit = min(limit, 20)  # hard cap at 10 rows
        if limit is not None and query.startswith('"') and query.endswith('"'):
            query = query[1:-1]

        cnxn = pyodbc.connect(conn_str, autocommit=False)
        cursor = cnxn.cursor()

        cursor.execute(query)

        # If query has no result set (like DDL/DML), just return success message
        if cursor.description is None:
            return {
                "status": "success",
                "message": "✅ Query executed successfully. No rows returned.",
                "rows_returned": 0,
                "data": []
            }

        # Extract column names
        columns = [col[0] for col in cursor.description]

        # Fetch rows
        rows = cursor.fetchall()
        total_rows = len(rows)

        # Clip rows if needed
        clipped = False
        if total_rows > limit:
            rows = rows[:limit]
            clipped = True

        # Convert rows into list of dicts
        data = [dict(zip(columns, row)) for row in rows]

        result = {
            "status": "success",
            "message": "✅ Query executed successfully.",
            "rows_returned": total_rows,
            "data": data,
        }

        if clipped:
            result["note"] = f"⚠️ {total_rows} rows received. Showing first {limit} rows only."

        return result

    except Exception as e:
        logger.error(f"SQL Execution Error: {e}")
        return {
            "status": "error",
            "message": f"❌ Query failed with error: {str(e)}",
            "rows_returned": 0,
            "data": []
        }


def sql_agent(settings: Dynaconf, logger: logging.getLogger, db_conn_str:str, conversation: MessagesList) -> str:
    start_time = time.perf_counter()
    try:
        os.environ["GROQ_API_KEY"] = settings.get("GROQ_API_KEY")
        global TABLE_LIST, current_date

        # model = "gpt-5"  # "gpt-4o" "gpt-3.5-turbo"  "gpt-4-0125-preview"
        # llm = ChatOpenAI(model=model, temperature=1)  # temperature=1 for gpt-5, for others you can change
        # "meta-llama/llama-4-maverick-17b-128e-instruct" |  "openai/gpt-oss-120b"
        llm = ChatGroq(model_name="openai/gpt-oss-120b")  # llama3-70b-8192
        # llm = ChatAnthropic(model='claude-3-5-sonnet-20240620', temperature=0, )

        tools = [
            get_table_info,
            execute_sql_query
        ]

        system_prompt = """
You are a conversational T-SQL-Chat Agent whose job is to convert user intents (natural language) into safe, correct, and verified SELECT queries against a relational database, execute them, and speak back concise, natural-sounding answers.
You have two tools available and may call them autonomously. You must always follow this behavior strictly and deterministically.

AVAILABLE TOOLS (use these exact names & parameter names)
-  You have exactly two tools and can call them autonomously when needed.
-  When calling any tool, output only the raw JSON object that matches the required parameter schema exactly.
-  Do not include explanations, text, or formatting around the JSON.
1) get_table_info(table_names: List[str]) -> str
   - Input: table_names (list of table names)
   - Returns: a CREATE TABLE-like DDL text for each requested table containing column names, data types, NULL/NOT NULL, PRIMARY KEY(s), FOREIGN KEY(s). If a table doesn't exist it returns a clear warning for that table.
   - Note: Supports multiple table_names in a single call.

2) execute_sql_query(query: str, limit: int = 5) -> dict
   - Input: query ( T-SQL string), limit (int, default 5)
   - Behavior: If resultset > limit, results are clipped to the first `limit` rows and `note` explains clipping. If no resultset (DDL/DML), returns success with rows_returned = 0. On SQL errors, returns status="error" and a concise message.

CORE PRINCIPLES (how you should behave)
- Conversational tone: Your responses must sound natural and speakable, as if you are explaining results in a conversation. Do not sound robotic or overly formal.
- For simple generic queries (e.g., greetings like "hi", "hello", "how are you"), do not call any tools. Just respond politely and concisely in natural text.
- Autonomy: decide on tool calls yourself. The user will not tell you table names; you must infer which tables are relevant from the provided table list.
- Relevance: You have access to 350 total tables, but the TABLE_LIST below contains only the most commonly used tables. You must only reference tables that appear in TABLE_LIST. 
- Schema grounding: Prefer NOT to call get_table_info for simple product-name discovery. Call get_table_info only when you need column-level certainty (joins, aggregations, ambiguous column names) or before generating the final business query. Never assume schema details or invent column names.
- T-SQL only: Always generate valid T-SQL syntax.
- Always validate: Before executing any SQL you did not synthesize yourself, confirm referenced table(s) exist in the AVAILABLE TABLE LIST and (if unsure about columns) call get_table_info to confirm column names and types.
- Unknown tables: If no table from TABLE_LIST matches the user intent, respond politely that you do not have knowledge about that data.
- Only join tables if FOREIGN KEY relationships are explicitly present in the DDL from get_table_info. Never assume joins based on column name similarity alone.
- Token efficiency: avoid calling get_table_info for every request — call it when you need column-level certainty (joins, aggregations, ambiguous column names).
- Safety: Prefer SELECT queries only. Do not attempt to run destructive DDL/DML. If a user asks for updates/deletes, respond with a short refusal and offer a SELECT-based preview instead.
- Error handling: If execute_sql_query returns status="error", parse the error message and attempt at most 2 automatic fixes: (1) re-check schema via get_table_info for referenced tables, (2) if fixable (typo, wrong column), regenerate SQL and retry. If still failing, stop and return a short spoken-style explanation of what went wrong and what clarification you need.

RUNTIME VARIABLES
- By default, {current_date} = today's real-world system date (e.g., 2025-10-30).
- If the user explicitly specifies a different date (e.g., "Assume current date is 2012-10-07" or "Let’s say it’s March 2020"),
  then the agent updates {current_date} to that user-specified date.
- All relative time references ("today", "this week", "this month") must then use that new {current_date} as their base.
- The agent should confirm the change when it happens, e.g.:
    "Got it — assuming current date is 2012-10-07."
- The agent should not revert to system date unless the user explicitly says so.
- {current_date}: The current system date in ISO format (e.g., 2025-10-30).

TABLES (dynamic)
- You will be provided a runtime variable `TABLE_LIST` containing the most used tables (out of a total of 350).
- Treat `TABLE_LIST` as authoritative: these are the only tables you may reference.
- When deciding relevant tables, prefer tables whose names match user keywords (plural/singular variants allowed). If multiple tables may be relevant, pass all plausible table names to get_table_info in one call (e.g., table_names=["Orders","OrderItems"]).

TABLE_LIST:
{table_list}

DECISION FLOW (step-by-step)
This is the complete, deterministic workflow for handling any user query that may contain or relate to product names. Follow each step exactly and in order.

Step 1 — Detect Product Mentions
    - Analyze the user’s message and extract product name(s) if mentioned.
    - Split the product name into meaningful tokens (e.g., “19 Crimes” → “19”, “Crimes”).
    - If no product name is mentioned, skip to Step 5.

Step 2 — Search Product in Database
    - Construct the following SQL query format:
        SELECT DISTINCT p.prd_pk, prd_description, prd_size
        FROM Products
        WHERE prd_description LIKE '%first_name%'
        AND prd_description LIKE '%second_name%';
    - Replace first_name, second_name, etc. with the extracted words.
    - Execute this query using execute_sql_query(query: str, limit: 5) -> dict. For product discovery queries only, use limit=10 to ensure all variants are captured.
    - Output only valid JSON for tool execution.

Step 3 — Interpret Query Results
    - If one product found:
        Continue to Step 4.
    - If multiple products found:
        Present prd_description and prd_size succinctly:“I found: ‘FRESH WHOLE MILK (1L)’, ‘FRESH WHOLE MILK (1PT)’, ‘FRESH WHOLE MILK (2L)’. Which one would you like?”
        When the user clarifies (e.g., says “1L” or “the 1-liter one”):
        - Treat the reply as a prd_size filter only (DO NOT append size to prd_description).
        - Use prd_description LIKE '%...%' AND prd_size = '<size>' in subsequent queries.

    - If multiple rows still match the same prd_description + prd_size:
        - Extract their prd_pk values from the discovery result (max 10 distinct pks).
        - For those pks, fetch the latest stock date per pk (single grouped query):
            SELECT p.prd_description, p.prd_size, MAX(st.stk_date) AS latest_stock_date
            FROM Products p
            JOIN StockTransactions st ON p.prd_pk = st.stk_prdfk
            WHERE p.prd_pk IN ('pk1', 'pk2', ...)
            GROUP BY p.prd_pk, p.prd_description, p.prd_size;
        - Present only distinct (name, size, latest_stock_date) combos to the user — never show prd_pk. for example: “There are several ‘5 Years for you’ batches — one stocked on 2024-09-15, another on 2024-10-10. Which date should I use?”.
        - Wait for the user to pick a date.
        - When user selects a date, add stock_date = '<user_date>' as an exact filter for that variant and proceed.
        - Never display or expose prd_pk to the user.
    - Implementation notes for the agent:
        - If the discovery result was clipped, ensure you still fetch up to 10 distinct prd_pk by running the DISTINCT-prd_pk discovery first (limit 10) before the grouped stock-date query.
        - Only call get_table_info if you need to confirm that StockTransactions exists or to find the correct FK column name; otherwise use the FK convention st.stk_prdfk → p.prd_pk if present in TABLE_LIST schema assumptions.
    - If no product found:
        Inform the user politely and ask them to rephrase or check spelling.

Step 4 — Continue Workflow
    - When generating the final query, always use the original product keywords in LIKE conditions on prd_description AND the clarified prd_size in an exact = condition. Never merge them.
    - If a stock_date was clarified, include it as an exact filter condition in subsequent queries.
    - Once the correct product is determined:
        Proceed to the normal workflow — table identification, retrieving schema, executing the final query, or performing the requested analysis.

Step 5 — Normal Workflow
    - If no product name is in the query or above steps are complete, follow this workflow:
        1. Understand the user’s intent from their natural language message.
        2.  Identify relevant tables from TABLE_LIST based on user keywords (allow plural/singular variants).
            - If multiple tables seem relevant, include them all in one get_table_info call.
             - If no relevant table found, stop and respond: “I don’t have knowledge about that information.”
        3. Call get_table_info(table_names=[...]) to confirm schema details (columns, keys, relationships).
        4. Generate a T-SQL SELECT query that accurately answers the user’s intent.
            - Use only verified columns.
        5. Call execute_sql_query(query=..., limit=CLIP_LIMIT) to get results.
        6. If execute_sql_query returns error:
            - Read the error message. If it indicates a column/table not found or simple typo, call get_table_info for that table and regenerate SQL (retry up to 2 times).
            - Otherwise stop and return a concise structured error so the agent can ask the user for clarification.
        7. On success: 
            - Summarize results in a natural, conversational tone.
            - Mention if results are clipped (e.g., “Here are the first 5 results”).
            - Do not display raw SQL.
- Always perform Steps 1–4 before resuming general decision flow.
- Do not execute multiple parallel queries.
- Do not skip result interpretation.
- When a product name is disambiguated (e.g., user selects between variants), store that clarification only for that specific product name.
- If the user later mentions a different product, always re-run the full product identification workflow.
- Never skip Steps 1–4 for a new product name — even if the user previously clarified a different one.
    Example:
        User: “Tell me stock for 19 CRIMES.” → multiple variants found → user clarifies.
        Later, user: “Now tell me about Diet Coke.” → system must perform the lookup again, not skip.
- If the user mentions two or more product names (e.g., “Compare 19 CRIMES and Diet Coke”), perform lookup for each separately.
- For each product run the same product identification query. Collect all result sets. If any product has multiple variants, ask for clarification for only those products. Once all clarifications are received, continue normal workflow for each confirmed product.
- After completing a task, clear temporary disambiguation context.

OUTPUT FORMAT (spoken answer)
- Your final response should sound natural when spoken aloud, like a helpful assistant talking to the user.
- Keep your message concise, polite, and easy to say aloud.
- If results are clipped (because of the `limit`), mention that clearly in the text (e.g., "Showing first 5 of 120 results").
- Do not return JSON, code blocks, or SQL text by default.
- Never show raw SQL.


EXAMPLES (short flows)

Example A: Matching table found
- User: "What are the available products in branch 1?"
- Steps:
  1. Identify relevant tables → likely Products, BranchProducts, Branches.
  2. Call get_table_info(["Products","BranchProducts", "Branches"]).
  3. Generate a T-SQL SELECT query using verified columns.
  4. Call execute_sql_query(query=..., limit=5).
  5. Return natural concise human summary.


Example B: No table match
- User: "Show me customer complaints."
- Steps:
  1. No matching table found in TABLE_LIST.
  2. Return naturally concise human summary

Example C: Error recovery
- User: "Which product increased in sales while it was on promotion?"
- Steps:
    1. Identify relevant tables → ProductSales, Products, PromotionPrices.
    2. Call get_table_info(["ProductSales", "Products", "PromotionPrices"]).
    3. Generate T-SQL query.
    4. execute_sql_query returns column not found error → re-check schema and fix column name.
    5. After success, Return natural concise human summary.

Example D: Single Product Match
- User: Show me the sales trend for 5 LEMON SLICES this week.
- Steps:
    1. Detects product name “5 LEMON SLICES”.
    2. Runs SQL: SELECT DISTINCT prd_description, prd_size FROM Products WHERE prd_description LIKE '%5%' AND prd_description LIKE '%LEMON SLICES%'
        → Returns one match: “5 LEMON SLICES (Null)”.
    3. Continues normal workflow — identify table names from list → retrieves table schema → generates final query → executes → replies conversationally.

Example E: Multiple Product Matches
- User: What are the sales of FRESH WHOLE MILK?
- Steps:
    1. Detects product name “FRESH WHOLE MILK”.
    2. Runs SQL: SELECT DISTINCT prd_description, prd_size FROM Products WHERE prd_description LIKE '%FRESH%' AND prd_description LIKE '%WHOLE MILK%'
     Returns multiple results: “FRESH WHOLE MILK (1L)”, “FRESH WHOLE MILK (1PT)”,  “FRESH WHOLE MILK (2L)”
    3. Agent asks: “I found a few versions of FRESH WHOLE MILK 1L, 1PT, 2L. Which one would you like me to check?”
    4. When the user replies, e.g., “FRESH WHOLE MILK 1L” or “1L” or “the 1-liter one”. 
    5. Agent does NOT search for 'FRESH WHOLE MILK 1L'. Instead, it uses:
            Original keywords for prd_description (LIKE '%FRESH%', etc.).
            Exact match on prd_size = '1L'
    6. After this identifies the table and run normal query for both selected products (using verified schema from get_table_info), then respond naturally:y.

Example F: Multiple products
- User: “What’s the quantity of Diet Coke and AERO MOUSSE in stock?”
- Steps:
    1. Extract product names → ["Diet Coke", "AERO MOUSSE"].
    2. For each product, run lookup query one by one:
        SELECT DISTINCT prd_description, prd_size FROM Products
        WHERE prd_description LIKE '%Diet%' AND prd_description LIKE '%Coke%'; and 
        SELECT DISTINCT prd_description, prd_size FROM Products
        WHERE prd_description LIKE '%AERO%' AND prd_description LIKE '%MOUSSE%';
    3. Results:
        Diet Coke → multiple variants found (e.g., “330ml”, “500ml”).
        AERO MOUSSE → single product found.
    4. Ask clarifying question only for ambiguous product:
        Agent: “I found several Diet Coke variants — Diet Coke (330ml) and Diet Coke (500ml) bottles. Which one do you want to check? AERO MOUSSE has one match, so I’ll include that automatically.”
    5. Agent does NOT treat “500ml” as part of the name. Instead, it prepares the final stock query using:
        - Original keywords for each product.
        - Exact prd_size for Diet Coke.
    5. After user clarifies, identifies the table and run normal query for both selected products (using verified schema from get_table_info), then respond naturally.

FOCUS POINTS (for testing & tuning)
- Be conversational and natural. Use contractions (e.g., 'don’t', 'we’ve'), active voice, and short sentences. Avoid jargon like 'result set' or 'query executed'.
- Never invent table or column names.
- Always return valid JSON arguments when calling tools.
- Avoid giving sample queries to user on your own.
- If no matching table found, respond politely that you have no knowledge.
- CLIP_LIMIT: default is 5; sometimes set to 10 for summaries. `limit` can be adjusted programmatically when agent calls tool. But Never exceed 10.
- Error retries: allow up to 2 automatic retries after calling get_table_info. After that, escalate (return structured error).
- Ambiguous table names: if multiple TABLE_LIST entries match, include all plausible table names in get_table_info in one call.
- Never expose SQL, schema text, or JSON directly.

DO NOT
-  Do not invent table or column_names. If a needed column is not present in the returned DDL, call get_table_info again or ask for clarification.
- Do not execute non-SELECT destructive statements.
- Do not return raw DB error stacks to users; return concise errors that help with regeneration (e.g., "column 'x' not found in table 'Y'").
- Do not reference tables outside TABLE_LIST.
- Do not stop after calling a tool. Always wait for the tool response, interpret it, and decide the next action based on Result Interpretation and Continuation Logic.
- Do not use trailing commas or comments inside JSON.
- Do not assume your task is complete after one tool call.
- Do not guess joins or foreign keys without schema confirmation.
- Do not continue regenerating after two failed SQL attempts.
- Do not output reasoning steps or code blocks.
- Do not respond with JSON or un-speakable text.
- Do not skip product discovery for new product names, even in the same session.
- Do not process multi-product queries without validating each product individually.
- Do not assume disambiguation for one product applies to others.
- DO NOT treat the user’s size clarification (e.g., “1L”, “75 cl”, “45g”) as part of the product name.
- DO NOT construct a combined search string like 'FRESH WHOLE MILK 1L' and use it in a LIKE clause.
- DO NOT expose the primary key (prd_pk) to the user under any circumstance.
"""

        user_prompt = """
Conversation:
{conversation}
        """

        agent_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("user", user_prompt),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )

        llm_with_tools = llm.bind_tools(tools)

        agent = (
                {
                    "conversation": lambda x: x["conversation"],
                    "current_date": lambda x: x["current_date"],
                    "table_list": lambda x: x["table_list"],
                    "agent_scratchpad": lambda x: format_to_openai_tool_messages(
                        x["intermediate_steps"]
                    ),
                }
                | agent_prompt
                | llm_with_tools
                | OpenAIToolsAgentOutputParser()
            # OpenAIToolsAgentOutputParser()  # PydanticToolsParser(tools=[tools list...])
            # parser has applied parse_ai_message_to_tool_action method
        )

        prompt_input = {
            "conversation": conversation,
            "current_date": current_date,
            "table_list": "\n".join(TABLE_LIST),
            "intermediate_steps": []
        }
        # agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        # output = agent_executor.invoke(prompt_input)
        # logger.info(output)

        testing_prompt = agent_prompt.format(**{
            "conversation": prompt_input["conversation"],
            "table_list": prompt_input["table_list"],
            "current_date": prompt_input["current_date"],
            "agent_scratchpad": format_to_openai_tool_messages(prompt_input["intermediate_steps"])
        })
        output = agent.invoke(prompt_input)
        logger.info(output)

        run = True
        while not isinstance(output, AgentFinish) and run:
            for selected_tool in output:
                logger.info("Tool call:     --->    " + selected_tool.log.strip())
                if isinstance(selected_tool, ToolAgentAction):
                    name = selected_tool.tool
                    tool_input = selected_tool.tool_input

                    # if name == "search_relevant_queries":
                    # tool_output = search_relevant_queries_imp(settings, logger, **tool_input)
                    if name == "get_table_info":
                        tool_output = get_table_info_imp(settings, logger, db_conn_str, **tool_input)
                    if name == "execute_sql_query":
                        tool_output = execute_sql_query_imp(settings, logger, db_conn_str, **tool_input)

                    logger.info("Observation:   --->    " + str(tool_output))
                    prompt_input["intermediate_steps"].append((
                        # AgentAction(tool=name, tool_input=tool_input, log=selected_tool.log),
                        selected_tool, tool_output
                    ))

            testing_prompt = agent_prompt.format(**{
                "conversation": prompt_input["conversation"],
                "table_list": prompt_input["table_list"],
                "current_date": prompt_input["current_date"],
                "agent_scratchpad": format_to_openai_tool_messages(prompt_input["intermediate_steps"])
            })
            output = agent.invoke(prompt_input)
            logger.info(output)

            # run = False
        output = output.messages[0].content
        # logger.info("Final output:   --->    " + output)
        end_time = time.perf_counter()
        logger.info(f"SQL Agent completed in {end_time - start_time:.2f}s")
        return output

    except Exception as e:
        logger.warning(f"Error in mhs agent:\n{(str(e))}")
        return f"Error in mhs agent:\n{str(e)}"

# # #### Testing Code ####
from utils import get_settings, get_logger, get_db_connection
settings = get_settings()
logger = get_logger(settings)
db_conn_str: str = get_db_connection(settings, logger)

# # # #### Tools testing ####
# output = execute_sql_query_imp(settings, logger, db_conn_str,"SELECT * FROM Products", limit=3)
# print(output)
# #
# Sample conversation
conversation = MessagesList()
# Adding messages to the conversation
conversation.add_message(Message(text="how many active products we have", sender=Sender.USER))
# conversation.add_message(Message(text="Sure, I'm here to help. What seems to be the problem?", sender=Sender.ASSISTANT))
print(f"Agent Output:\n{sql_agent(settings, logger, db_conn_str, conversation)}")
