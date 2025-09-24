"""
Langchain agent of SQL Assistant.
"""
import logging
import os
import pyodbc
from pprint import pprint
from dynaconf import Dynaconf
from typing import List, Optional, Dict, Any
from langchain.agents.format_scratchpad import format_to_tool_messages
from langchain.agents.output_parsers.tools import ToolAgentAction, parse_ai_message_to_tool_action
from langchain.pydantic_v1 import BaseModel, Field
from langchain.tools import BaseTool, StructuredTool, tool

from langchain.agents import AgentExecutor
from langchain_core.agents import AgentFinish, AgentAction
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.output_parsers.openai_tools import PydanticToolsParser
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
from langchain.agents.format_scratchpad.openai_tools import (format_to_openai_tool_messages)
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser

from data_models import MessagesList, Message, Sender
from vector_database_manager import load_embedding_model, create_vector_db_collection, check_and_load_query_data, \
    search_client_queries

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
    "BranchProducts"
]


def initialize_client_sql_queries_vector_database(settings: Dynaconf, logger: logging.getLogger):
    """Load embedding model and initialize vector database."""
    load_embedding_model(logger)
    create_vector_db_collection(settings)
    check_and_load_query_data(settings, logger)


class SearchRelevantQueryInput(BaseModel):
    search_query: str = Field(
        description="Natural language query from the user for which we want to find similar past queries."
    )


@tool("search_relevant_queries", args_schema=SearchRelevantQueryInput, return_direct=False)
def search_relevant_queries(search_query: str) -> str:
    """
    Search previously stored user queries to find relevant examples.
    Returns both the matched natural language queries and their corresponding SQL queries.
    Useful for guiding SQL generation by leveraging past successful queries.
    """
    pass


def search_relevant_queries_imp(
        settings: Dynaconf, logger: logging.Logger, search_query: str
) -> str:
    """
    Search ChromaDB for relevant past user queries and return both user and SQL queries.
    """
    try:
        # Assume you already have a helper for ChromaDB semantic search
        # Something like: search_queries_in_chroma(settings, logger, query=search_query)
        results = search_client_queries(settings, logger, query=search_query)

        if not results or len(results) == 0:
            return "No relevant past queries found."

        # Format results for agent
        formatted = []
        formatted.append(
            f"Found {len(results)} queries using vector search.\n"
            "These examples may or may not match the current request. "
            "If useful, reuse or adapt them. "
            "If not relevant, ignore and generate a new SQL query.\n"
        )

        for r in results:
            user_q = r.get("client_query", "N/A")
            sql_q = r.get("sql_query", "N/A").replace("\n", " ").strip()
            meta = r.get("meta", None)

            block = f"User Query: {user_q}\nSQL Query: {sql_q}"
            if meta:
                block += f"\nMetadata: {meta}"
            formatted.append(block)

        return "\n\n".join(formatted)

    except Exception as e:
        logger.error(f"Error searching relevant queries: {e}")
        return f"❌ Failed to search relevant queries. Error: {e}"


class GetTableInfoInput(BaseModel):
    table_names: List[str] = Field(
        description="List of table names for which schema details (columns, data types, primary keys, foreign keys) are required."
    )


@tool("get_table_info", args_schema=GetTableInfoInput, return_direct=False)
def get_table_info(table_names: List[str]) -> str:
    """
    Use this tool to retrieve schema details of one or more database tables.
    The tool returns a CREATE TABLE DDL representation that includes columns,
    data types, primary keys, and foreign key constraints.
    """
    pass


def get_table_info_imp(
        settings: Dynaconf, logger: logging.Logger, table_names: List[str]
) -> str:
    """
    Retrieve schema details for given table(s) from SQL Server database.
    Returns CREATE TABLE DDL statements for each requested table.
    """

    if not table_names or len(table_names) == 0:
        return "❌ No table names provided."

    try:
        # Reuse your pyodbc connection string style
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={settings.DB_SERVER};"
            f"DATABASE={settings.DB_NAME};"
            f"Trusted_Connection=yes;"
            f"TrustServerCertificate=yes;"
        )

        cnxn = pyodbc.connect(conn_str, autocommit=False)
        cursor = cnxn.cursor()

        output = []

        for table in table_names:
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

            # Build CREATE TABLE string
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
                ddl_lines.append(
                    f"    FOREIGN KEY ({col}) REFERENCES {ref_table}({ref_col})"
                )

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


def execute_sql_query_imp(
        settings: Dynaconf, logger: logging.Logger, query: str, limit: int = 5
) -> Dict[str, Any]:
    """
    Execute an SQL query and return structured results.
    - If query fails: return structured error.
    - If results exceed `limit`: return only first `limit` rows and note clipping.
    """

    try:
        limit = min(limit, 10)  # hard cap at 10 rows
        if query.startswith('"') and query.endswith('"'):
            query = query[1:-1]
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={settings.DB_SERVER};"
            f"DATABASE={settings.DB_NAME};"
            f"Trusted_Connection=yes;"
            f"TrustServerCertificate=yes;"
        )
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


def sql_agent(settings: Dynaconf, logger: logging.getLogger, conversation: MessagesList) -> str:
    try:
        os.environ["OPENAI_API_KEY"] = settings.get("OPENAI_API_KEY")
        global TABLE_LIST

        model = "gpt-5"  # "gpt-4o" "gpt-3.5-turbo"  "gpt-4-0125-preview"
        llm = ChatOpenAI(model=model, temperature=1)  # temperature=1 for gpt-5, for others you can change
        # llm = ChatGroq(temperature=0, model_name="llama-3.1-70b-versatile")  # llama3-70b-8192
        # llm = ChatAnthropic(model='claude-3-5-sonnet-20240620', temperature=0, )

        tools = [
            search_relevant_queries,
            get_table_info,
            execute_sql_query
        ]

        system_prompt = """
You are a SQL-Chat Agent whose job is to convert user intents (natural language) into safe, correct SELECT queries against a relational database and return results. You have three tools available and may call them autonomously.

AVAILABLE TOOLS (use these exact names & parameter names)
1) get_table_info(table_names: List[str]) -> str
   - Input: table_names (list of table names)
   - Returns: a CREATE TABLE-like DDL text for each requested table containing column names, data types, NULL/NOT NULL, PRIMARY KEY(s), FOREIGN KEY(s). If a table doesn't exist it returns a clear warning for that table.
   - Note: Supports multiple table_names in a single call.

2) search_relevant_queries(search_query: str) -> list
   - Input: search_query (the user's natural language query)
   - Returns: a list of matches; each match is a structured item with fields: client_query (text), sql_query (the previously generated SQL), distance (similarity). If none found returns an empty list or a clear "no results" message.

3) execute_sql_query(query: str, limit: int = 5) -> dict
   - Input: query (SQL string), limit (int, default 5)
   - Behavior: If resultset > limit, results are clipped to the first `limit` rows and `note` explains clipping. If no resultset (DDL/DML), returns success with rows_returned = 0. On SQL errors, returns status="error" and a concise message.

CORE PRINCIPLES (how you should behave)
- Autonomy: decide on tool calls yourself. The user will not tell you table names; you must infer which tables are relevant from the provided table list.
- For simple generic queries (e.g., greetings like "hi", "hello", "how are you"), do not call any tools. Just respond politely and concisely in natural text.
- Use search_relevant_queries FIRST when the user intent is similar to past queries. If a relevant match is found, consider reusing its sql_query — but **validate** it before executing.
- Always validate: Before executing any SQL you did not synthesize yourself, confirm referenced table(s) exist in the AVAILABLE TABLE LIST and (if unsure about columns) call get_table_info to confirm column names and types.
- Token efficiency: avoid calling get_table_info for every request — call it when you need column-level certainty (joins, aggregations, ambiguous column names).
- Safety: Prefer SELECT queries only. Do not attempt to run destructive DDL/DML. If a user asks for updates/deletes, respond with a short refusal and offer a SELECT-based preview instead.
- Error handling: If execute_sql_query returns status="error", parse the error message and attempt at most 2 automatic fixes: (1) re-check schema via get_table_info for referenced tables, (2) if fixable (typo, wrong column), regenerate SQL and retry. If still failing, return a concise structured error to the caller explaining what failed and why.

TABLES (dynamic)
- You will be provided a runtime variable `TABLE_LIST` (an exhaustive list of table names available in the DB).
- Treat `TABLE_LIST` as authoritative: these are the only tables you may reference.
- When deciding relevant tables, prefer tables whose names match user keywords (plural/singular variants allowed). If multiple tables may be relevant, pass all plausible table names to get_table_info in one call (e.g., table_names=["Orders","OrderItems"]).

Below are the tables that are present in our Database.
TABLE_LIST:
{table_list}

DECISION FLOW (step-by-step)
1. Parse user intent and extract a short `search_query` (the user text).
2. Call search_relevant_queries(search_query=search_query).
   - If results non-empty and a top-match has clearly high relevance (you judge it as applicable), inspect its `sql_query`.
     - Validate the `sql_query` against TABLE_LIST and use get_table_info for any tables referenced if you are unsure about column names.
     - If valid, call execute_sql_query(query=sql_query, limit=CLIP_LIMIT) to run it.
   - If no suitable match found, proceed to (3).
3. Identify likely tables from TABLE_LIST. If column-level detail is required, call get_table_info(table_names=[...]) to get DDL and decide column names and joins.
4. Synthesize a clear, minimal SELECT query that answers the user's intent. Avoid unnecessary columns and avoid ambiguous column references.
5. Call execute_sql_query(query=your_query, limit=CLIP_LIMIT).
6. If execute_sql_query returns error:
   - Read the error message. If it indicates a column/table not found or simple typo, call get_table_info for that table and regenerate SQL (retry up to 2 times).
   - Otherwise stop and return a concise structured error so the agent can ask the user for clarification.
7. On success: produce a concise human-readable answer and include the structured result for downstream use.


OUTPUT FORMAT (how you should present results to the user)
- Always return a **concise natural language text answer**.
- If results are clipped (because of the `limit`), mention that clearly in the text (e.g., "Showing first 5 of 120 results").
- Do not return JSON or structured output — only user-friendly text.


EXAMPLES (short flows)

Example A: Relevant past query found and usable
- User: "How many WALLS MAGNUM CHILL are in stock?"
- Steps:
  1. Extract intent → search_query="How many WALLS MAGNUM CHILL are in stock?"
  2. Call search_relevant_queries(search_query=...) → returns a strong match with both client_query and sql_query.
  3. Validate that the retrieved sql_query fully answers the user’s request.
     - If yes, identify tables used, e.g., ["Products","BranchProducts"].
     - Optionally confirm with get_table_info(["Products","BranchProducts"]) if schema is needed.
  4. Call execute_sql_query(query=..., limit=5).
  5. Return concise human summary


Example B: Past query found but not relevant
- User: "Show me top 5 suppliers by purchase orders last month."
- Steps:
  1. Extract intent → search_query="top 5 suppliers by purchase orders last month".
  2. Call search_relevant_queries(search_query=...) → returns a past query but on close inspection it does **not** answer the user’s request.
  3. Ignore the irrelevant sql_query.
  4. Identify relevant tables from TABLE_LIST, e.g., ["Suppliers","PurchaseOrders","PurchaseOrderlines"].
  5. Call get_table_info([...]) to confirm columns and relationships.
  6. Generate a new SQL query tailored to the request.
  7. Call execute_sql_query(query=..., limit=5).
  8. Return concise human summary

Example C: No past query found
- User: "What is the slowest selling product this year?"
- Steps:
  1. Extract intent → search_query="slowest selling product this year".
  2. Call search_relevant_queries(search_query=...) → no relevant match found.
  3. Identify likely relevant tables from TABLE_LIST, e.g., ["ProductSales","Products"].
  4. Call get_table_info(["ProductSales","Products"]) to understand available columns (e.g., sales quantity, product description, dates).
  5. Generate a new SQL query using schema details.
  6. Call execute_sql_query(query=..., limit=5).
  7. Return concise human summary


FOCUS POINTS (for testing & tuning)
- Avoid giving sample queries to user on your own.
- Relevance threshold: tune how aggressive you are in reusing historical queries. If uncertain, prefer validation via get_table_info.
- CLIP_LIMIT: default is 5; sometimes set to 10 for summaries. `limit` can be adjusted programmatically when agent calls tool.
- Error retries: allow up to 2 automatic retries after calling get_table_info. After that, escalate (return structured error).
- Ambiguous table names: if multiple TABLE_LIST entries match, include all plausible table names in get_table_info in one call.
- Keep final user-facing messages short and actionable.

DO NOT
- Do not invent table or column names. If a needed column is not present in the returned DDL, call get_table_info again or ask for clarification.
- Do not execute non-SELECT destructive statements.
- Do not return raw DB error stacks to users; return concise errors that help with regeneration (e.g., "column 'x' not found in table 'Y'").
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
            "table_list": "\n".join(TABLE_LIST),
            "intermediate_steps": []
        }
        # agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        # output = agent_executor.invoke(prompt_input)
        # logger.info(output)

        testing_prompt = agent_prompt.format(**{
            "conversation": prompt_input["conversation"],
            "table_list": prompt_input["table_list"],
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

                    if name == "search_relevant_queries":
                        tool_output = search_relevant_queries_imp(settings, logger, **tool_input)
                    if name == "get_table_info":
                        tool_output = get_table_info_imp(settings, logger, **tool_input)
                    if name == "execute_sql_query":
                        tool_output = execute_sql_query_imp(settings, logger, **tool_input)

                    logger.info("Observation:   --->    " + str(tool_output))
                    prompt_input["intermediate_steps"].append((
                        # AgentAction(tool=name, tool_input=tool_input, log=selected_tool.log),
                        selected_tool, tool_output
                    ))

            testing_prompt = agent_prompt.format(**{
                "conversation": prompt_input["conversation"],
                "table_list": prompt_input["table_list"],
                "agent_scratchpad": format_to_openai_tool_messages(prompt_input["intermediate_steps"])
            })
            output = agent.invoke(prompt_input)
            logger.info(output)

            # run = False
        output = output.messages[0].content
        # logger.info("Final output:   --->    " + output)
        return output
    except Exception as e:
        logger.warning(f"Error in mhs agent:\n{(str(e))}")
        return f"Error in mhs agent:\n{str(e)}"

# # #### Testing Code ####
# from utils import get_settings, get_logger
#
# settings = get_settings()
# logger = get_logger(settings)
# initialize_client_sql_queries_vector_database(settings, logger)
#
# # #### Tools testing ####
# # output = search_relevant_queries_imp(settings, logger, "How many coca cola 1.5 liter are in stock?")
# # output = get_table_info_imp(settings, logger, ["ProductSales", "non_existing_table"])
# # output = execute_sql_query_imp(settings, logger, "SELECT * FROM ProductSalesh", limit=3)
# # pprint(output)
# #
# # Sample conversation
# conversation = MessagesList()
#
# # Adding messages to the conversation
# conversation.add_message(Message(text="please tell me, how many WALLS MAGNUM CHILL are in stock?", sender=Sender.USER))
# # conversation.add_message(Message(text="Sure, I'm here to help. What seems to be the problem?", sender=Sender.ASSISTANT))
# print(f"Agent Output:\n{sql_agent(settings, logger, conversation)}")
