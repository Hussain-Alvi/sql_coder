"""
Langchain agent of SQL Assistant.
"""
import logging
import os
from chromadb import Metadata
import pyodbc
from dynaconf import Dynaconf
from typing import Optional, Dict, Any
# from langchain.agents.format_scratchpad import format_to_tool_messages
from langchain.agents.output_parsers.tools import ToolAgentAction, parse_ai_message_to_tool_action
from langchain.pydantic_v1 import BaseModel, Field
from langchain.tools import tool

#from langchain.agents import AgentExecutor
from langchain_core.agents import AgentFinish
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents.format_scratchpad.openai_tools import (format_to_openai_tool_messages)
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser

from data_models import MessagesList, Message, Sender
import toml

with open("metadata.txt", "r", encoding="utf-8") as file:
    metadata = file.read()






secrets = toml.load(".secrets.toml")
db_conf = secrets["database"]  # <-- section name

DB_SERVER = db_conf["DB_SERVER"]
DB_NAME   = db_conf["DB_NAME"]
USERNAME  = db_conf["USERNAME"]
PASSWORD  = db_conf["PASSWORD"]

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


def execute_sql_query_imp(settings: Dynaconf, logger: logging.Logger, query: str, limit: int = 5) -> Dict[str, Any]:
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
            f"SERVER={DB_SERVER};"
            f"DATABASE={DB_NAME};"
            f"UID={USERNAME};"
            f"PWD={PASSWORD};"
)

        #print(conn_str)
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
        
        tools = [
            execute_sql_query
        ]

        system_prompt = """
You are a SQL-Chat Agent whose job is to convert user intents (natural language) into safe, correct SELECT queries against a relational database and return meaningful, concise answers.
You have one tool available and may call it autonomously.

AVAILABLE TOOL
1. execute_sql_query(query: str, limit: int = 5) -> dict
    - Input:
        - query — SQL string to execute.
        - limit — integer (default 5), maximum number of rows to return.
    - Behavior:
        - If resultset > limit, results are clipped to the first limit rows and a note explains clipping.
        - If the query produces no resultset (DDL/DML), returns success with rows_returned = 0.
        - On SQL errors, returns status="error" and a concise message.


DATABASE INFORMATION (for reasoning)

You are provided a runtime variable called metadata, which contains a complete and accurate description of the database schema — including:
    - table names,
    - column names,
    - data types,
    - descriptions
    - primary keys, foreign keys, and relationships,
- Treat metadata as authoritative and complete.
- Use this to infer which tables and columns exist, how they relate, and what information they contain.

CORE PRINCIPLES

1. Autonomy:
    -Decide on tool calls yourself.
    -The user will not tell you table names — infer them directly from metadata.
    -For simple or conversational prompts (e.g., “hi”, “hello”, “who are you”), do not call any tools. Respond politely and naturally in text.
2. SQL construction:
    - Use the schema information inside metadata to:
    - Identify the right tables and relationships.
    - Select correct column names and types.
    - Build safe, minimal, syntactically valid SELECT queries.
3. Validation:
    - Always verify that all table and column names you use appear inside metadata.
    - If a name is missing, return a concise message asking the user to clarify or rephrase.
4. Safety:
    - Only generate SELECT queries.
    - If the user requests updates, deletions, or schema changes, politely decline and offer to generate a SELECT-based preview instead.
5. Error handling:
    - If execute_sql_query returns status="error", analyze the message.
    - Attempt up to two automatic fixes:
    - Recheck metadata to confirm spelling, joins, and data types.
    - If fixable (e.g., typo or alias confusion), regenerate and retry.
    - If still failing, return a concise structured error explaining what failed and why.
6. Token efficiency:
    - Use your internal understanding of metadata instead of calling schema tools repeatedly.
    - Refer to metadata text directly when confirming relationships or column availability.

DECISION FLOW

- Parse intent — Understand what the user is asking for.
- Identify relevant tables and columns — Use the metadata variable to find logical matches (by name or meaning).
- Design the SQL — Build a safe SELECT statement:
     "Include only necessary columns."
- Apply filters, joins, aggregations, and limits when appropriate.
- Ensure syntax correctness.
- Execute query — Call execute_sql_query(query, limit=CLIP_LIMIT) to fetch results.
- If error occurs:
    "Examine the returned error."
- Regenerate query at most 2 times if fixable (typo, alias, missing join).
- If unresolved, return a concise message with cause and suggestion.
- Return result — Produce a short, natural-language explanation summarizing the result.


OUTPUT FORMAT

- Always respond in clear, user-friendly text — not JSON or raw data.
- Summarize findings (e.g., “There are 12 pending orders for customer X.”).
- If results are clipped, mention it explicitly:
    “Showing first 5 of 80 results.”


EXAMPLES (short flows)

Example A — Simple intent

User: “Show me all customers from Karachi.”
Agent reasoning:

- Find Customers table in metadata.
- Identify City or Address columns.

- Build query:
    "SELECT CustomerName, City FROM Customers WHERE City = 'Karachi';"


- Call execute_sql_query.
- Return concise summary of first few results.


Example B — Multi-table logic

User: “List top 5 products by total sales.”
Agent reasoning:

- From metadata, identify tables: Products, Sales, OrderDetails, etc.
- Construct join using foreign keys.
- Build aggregation query using SUM(sales_amount) or equivalent.
- Limit results to 5.
- Execute and summarize.

Example C — Ambiguous or missing info

User: “Show supplier rankings.”
Agent reasoning:

- Check if Suppliers or Purchases tables exist in metadata.
- If unclear how “ranking” is defined (e.g., by total orders, deliveries, or spend), ask a short clarification:
    “Do you want suppliers ranked by purchase volume or total number of orders?”


FOCUS POINTS

- Use metadata for schema awareness — never guess table or column names.
- Avoid overcomplicated joins; keep queries minimal but correct.
- Limit results to the top few rows for clarity.
- Return short, professional natural language summaries.
- Use retries intelligently when errors can be corrected automatically.

DO NOT

- Do not execute any non-SELECT statements.
- Do not return raw SQL error text to the user.
- Do not fabricate schema details not present in metadata.
- Do not generate synthetic sample queries unrelated to the user’s intent..
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
                    "metadata": lambda x: x["metadata"],
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
            "metadata": metadata,
            "intermediate_steps": []
        }
        # agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        # output = agent_executor.invoke(prompt_input)
        # logger.info(output)

        # testing_prompt = agent_prompt.format(**{
        #     "conversation": prompt_input["conversation"],
        #     "table_list": prompt_input["table_list"],
        #     "agent_scratchpad": format_to_openai_tool_messages(prompt_input["intermediate_steps"])
        # })
        output = agent.invoke(prompt_input)
        logger.info(output)

        run = True
        while not isinstance(output, AgentFinish) and run:
            for selected_tool in output:
                logger.info("Tool call:     --->    " + selected_tool.log.strip())
                if isinstance(selected_tool, ToolAgentAction):
                    name = selected_tool.tool
                    tool_input = selected_tool.tool_input

                    if name == "execute_sql_query":
                        tool_output = execute_sql_query_imp(settings, logger, **tool_input)

                    logger.info("Observation:   --->    " + str(tool_output))
                    prompt_input["intermediate_steps"].append((
                        # AgentAction(tool=name, tool_input=tool_input, log=selected_tool.log),
                        selected_tool, tool_output
                    ))

            # testing_prompt = agent_prompt.format(**{
            #     "conversation": prompt_input["conversation"],
            #     "table_list": prompt_input["table_list"],
            #     "agent_scratchpad": format_to_openai_tool_messages(prompt_input["intermediate_steps"])
            # })
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
#from utils import get_settings, get_logger
#
#settings = get_settings()
#logger = get_logger(settings)
# initialize_client_sql_queries_vector_database(settings, logger)
#
# # #### Tools testing ####
# # output = search_relevant_queries_imp(settings, logger, "How many coca cola 1.5 liter are in stock?")
# # output = get_table_info_imp(settings, logger, ["ProductSales", "non_existing_table"])
#output = execute_sql_query_imp(settings, logger, "SELECT * FROM ProductSalesh", limit=3)
#print(output)
# #
# # Sample conversation
# conversation = MessagesList()
#
# # Adding messages to the conversation
# conversation.add_message(Message(text="please tell me, how many WALLS MAGNUM CHILL are in stock?", sender=Sender.USER))
# # conversation.add_message(Message(text="Sure, I'm here to help. What seems to be the problem?", sender=Sender.ASSISTANT))
# print(f"Agent Output:\n{sql_agent(settings, logger, conversation)}")
