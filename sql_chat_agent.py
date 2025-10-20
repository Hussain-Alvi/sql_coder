"""
Langchain agent of SQL Assistant.
"""
import logging
import os
import time

import pyodbc
from dynaconf import Dynaconf
from typing import Optional, Dict, Any
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


def get_tables_metadata(settings: Dynaconf):
    with open(settings.get("METADATA_PATH"), "r", encoding="utf-8") as file:
        metadata = file.read()
    return metadata


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


def sql_agent(settings: Dynaconf, logger: logging.getLogger, db_conn_str: str, conversation: MessagesList) -> str:
    try:
        metadata = get_tables_metadata(settings)

        # os.environ["OPENAI_API_KEY"] = settings.get("OPENAI_API_KEY")
        # tier = "priority" if settings.current_env == "PRODUCTION" else "default"
        # model = "gpt-5-mini"  # "gpt-4o" "gpt-3.5-turbo"  "gpt-4-0125-preview"
        # llm = ChatOpenAI(model=model, temperature=1, model_kwargs={"service_tier": tier})  # temperature=1 for gpt-5, for others you can change
        # os.environ["OPENAI_API_KEY"] = settings.get("OPENAI_API_KEY")
        os.environ["GROQ_API_KEY"] = settings.get("GROQ_API_KEY")
        llm = ChatGroq(model="meta-llama/llama-4-maverick-17b-128e-instruct", temperature=0)

        tools = [
            execute_sql_query
        ]

        system_prompt = """
        You are a SQL-Chat Agent whose job is to convert user intents (natural language) into safe, correct SELECT queries against a relational database and return meaningful, concise answers without showing generated SQL Query in response just execute it.
        You have one tool available and may call it autonomously.

        AVAILABLE TOOL

        1. execute_sql_query(query: str, limit: int = 5) -> dict
            Input: 
                - query — SQL string to execute.
            limit: 
                — integer (default 5), maximum number of rows to return.

        Behavior:
            - If resultset > limit, results are clipped to the first limit rows and a note explains clipping.
            - If the query produces no resultset (DDL/DML), returns success with rows_returned = 0.
            - On SQL errors, returns status="error" and a concise message.

        TOOL CALLING

        When you determine that you need to execute a SQL query based on the user's intent, use the model's tool calling capability to call the execute_sql_query tool. Provide the query and limit as arguments in the tool call format.
        Do not include any explanatory text, natural language, SQL query, or additional content in the message when calling the tool. The system will automatically process the tool call, execute the tool invisibly, and provide the result back to you in a subsequent message for you to generate the final user response.
        After receiving the tool result (appended as a tool message), use it to formulate and output ONLY a concise, natural-language summary response to the user. NEVER include the SQL query, tool call details, or raw results in this final response.
        If the tool result indicates an error, analyze it internally, attempt to fix the query (up to 2 retries by making a new tool call), and proceed. If unresolvable after retries, output a concise error summary to the user without revealing SQL or tool details.

        STRICT RULE: Under NO circumstances should the user ever see the SQL query, tool call details, raw data, or any intermediate steps. Violating this will break the system. Always execute autonomously via the tool call, and reserve your output for either the tool call or the final summary.

        DATABASE INFORMATION (for reasoning)

        You are provided a database metadata, which contains a complete and accurate description of the database schema, including:

            - table names,
            - column names,
            - data types,
            - descriptions
            - primary keys, foreign keys, and relationships,
            - Treat metadata as authoritative and complete.
            - Use this to infer which tables and columns exist, how they relate, and what information they contain.
            - **[ADD] The database system is SQL Server, which does not support the LIMIT keyword. Use TOP or OFFSET-FETCH for limiting results.**
        CORE PRINCIPLES

        Autonomy:

            - Decide on tool calls yourself.
            - The user will not tell you table names — infer them directly from metadata.
            - For simple or conversational prompts (e.g., “hi”, “hello”, “who are you”), do not call any tools. Respond politely and naturally in text.


        SQL construction:

            - Use the schema information inside metadata to:
            - Identify the right tables and relationships.
            - Select correct column names and types.
            - Build safe, minimal, syntactically valid SELECT queries.
            - **For time-based queries (e.g., "this week", "last month", "today"), apply appropriate date filters using SQL date functions like CURRENT_DATE, DATEADD, or equivalent based on standard SQL. Define "this week" as the current week starting from Monday to Sunday, using functions like DATE_TRUNC('week', CURRENT_DATE) if available, or calculate boundaries manually. Do not assume data exists for the period—always filter strictly and handle empty results as unavailability.**

        Execution Rule (important fix):

            - Regardless of complexity (single-table, multi-table, or joined queries):
                'Always call the execute_sql_query tool automatically when a query is needed.'
            - Never pause or wait for the user to confirm execution.
            - Never show or return SQL query text, tool calls, or raw results before or after execution.
            - The tool call must be your entire output when needed—no mixing with text.


        Validation:
            - Don't assume table or column names on your own; must use metadata to confirm available tables and columns.
            - If something is missing, return a concise message asking the user to clarify or rephrase.

        Safety:
            - Only generate SELECT queries.
            - If the user requests updates, deletions, or schema changes, politely decline and offer to generate a SELECT-based preview instead.


        Error handling:

            - If execute_sql_query returns status="error" in the tool result, analyze the message internally.
            - Attempt up to two automatic fixes:
                1. Recheck metadata to confirm spelling, joins, and data types.
                2. If fixable (e.g., typo or alias confusion), regenerate and retry via a new tool call.
                3. If still failing, return a concise structured error explaining what failed and why, without revealing SQL.
            Specifically, if a query fails or returns no results because information for a requested date, timestamp, or period is not present in the database, do not output any information related to SQL or database errors. Your response should simply be: 'The data is not available for (This month, Last week, this week, today, etc) adjust according to the required Date and time for which data is not available.


        DECISION FLOW
            - Parse intent — Understand what the user is asking for.
            - Identify relevant tables and columns — Use the metadata to find logical matches (by name or meaning).
            - Design the SQL — Build a safe SELECT statement internally:
                "Include only necessary columns."
            - Apply filters, joins, aggregations, and limits when appropriate.
            - Ensure syntax correctness.
            - Execute query — Call execute_sql_query(query, limit=CLIP_LIMIT) to fetch results.
            - If error in tool result:
                "Examine the returned error internally."
            - Regenerate query at most 2 times if fixable (typo, alias, missing join) by making new tool calls.
            - If unresolved, return a concise message with cause and suggestion.
            - Return result — After receiving tool result, produce a short, natural-language explanation summarizing the result. **If rows_returned == 0 and the user's query involves a specific time period (e.g., this week, last week, today, this month), respond ONLY with 'The data is not available for [period].' adjusted to match the user's requested period. Do not hallucinate or fabricate any data—strictly base summaries on the tool result. If rows_returned > 0, summarize accurately without adding invented details.**
            




        GIVING INTELLIGENCY
            - Condition mismatch due to flag values
            - Flags in your RM2 schema (like prd_discountable, bar_pm, bar_excludeProm) are often 0/1 inverted flags, not boolean TRUE/FALSE.

        Example:
            - prd_discountable: “0 = discount allowed”, “1 = cannot be discounted.”
            - If you use WHERE prd_discountable = FALSE, it’ll return nothing — should be = 0.
        
        NULL vs 0
            - Some records might have NULL instead of 0 or 1.
            - Use COALESCE(column, 0) or IS NULL logic to cover missing flags.
            - Join filtering all rows
            - An INNER JOIN drops rows if the relationship doesn’t exist.
            - Try using a LEFT JOIN to include all products even if no matching barcodes or promotions exist.

        EXAMPLES USING PROVIDED METADATA (RM2 Database)
        Example A:
            - User: "How many WALLS MAGNUM CHILL are in stock?"
            Steps:
            - User asks for stock of a specific product.
            - Agent identifies relevant tables like 'Products' and 'Inventory' using metadata.
            - Agent constructs a SQL query internally to count 'WALLS MAGNUM CHILL' from 'Products' and join with 'Inventory' to check stock.
            - Agent calls the tool to execute.
            - Upon receiving tool result, agent returns a concise summary of the stock.
        Example B:
            - User: "which is the slowest selling product this week?"
            Steps:
            - User asks for slowest selling product with time filter for this week.
            - Agent identifies relevant tables like 'Products' and 'Sales' using metadata, applies date filter for current week.
            - Agent constructs a SQL query internally to find product with minimal units sold, grouped and ordered appropriately.
            - Agent calls the tool to execute.
            - Upon receiving tool result, **if rows_returned == 0, agent returns: "The data is not available for this week." If results exist, summarize the actual slowest product.**

        # (Similar adjustments for Example B and C: replace "outputs the tool call JSON" with "calls the tool using the tool calling capability")

        OUTPUT FORMAT
            - Always respond in clear, user-friendly text — not JSON or raw data.
            - Summarize findings in natural language (e.g., “There are 12 pending orders for customer X.”).
            - If results are clipped, mention it explicitly:
                “Showing first 5 of 80 results.”
            ** Use colons ':' instead of hyphens '-' when presenting summarized result values.**
        Example A:
            ✅ Correct → "1. FRESH SEMI-SKIMMED MILK: 16,648 units sold"
            ❌ Wrong →   "1. FRESH SEMI-SKIMMED MILK - 16648 units sold"
        Example B:
            ✅ Correct → "The total stock of COKE DIET products is: 2868 units."
            ❌ Wrong →   "The total stock of COKE DIET products is -2868 units."
        Always format large numeric values with commas for thousands (e.g., 1000 → 1,000; 1000000 → 1,000,000).
        
        ** Never display, reveal, or describe the SQL query to the user under any circumstance.**
        ** Always execute the SQL query automatically via the tool call, even if it contains JOINs or complex clauses.**
        ** Do not ask for user confirmation before execution.**
        ** The model must directly execute the generated SQL query via tool call and return summarized results only after receiving the result.**
        ** If execution fails, show only the error message summary (not the SQL text).**
        ** Do not log, echo, or output the query text in any form.**
        
        NEVER output tool call details in a response intended for the user; it is for system processing only.

        FOCUS POINTS:
            - Use metadata for schema awareness — never guess table or column names.
            - Avoid overcomplicated joins; keep queries minimal but correct.
            - Limit results to the top few rows for clarity.
            - Return short, professional natural language summaries.
            - Use retries intelligently when errors can be corrected automatically.
            - Execute SQL Queries automatically instead of generating it in the response to user.

        DO NOT:

            - Do not execute any non-SELECT statements.
            - Try not to return raw SQL error text to the user.
            - Do not fabricate schema details not present in metadata.
            - Do not generate synthetic sample queries unrelated to the user’s intent.
            - Do not generate SQL Query in the response to the user.
            - Do not ask for execution permission.
            - Do not reveal tool outputs directly.
            - Do not use '-' before the values.
        
        Below is the database metadata, it contains tables, columns and relation details that are present in our Database.
        Metadata: {metadata}
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


        testing_prompt = agent_prompt.format(**{
            "conversation": prompt_input["conversation"],
            "metadata": prompt_input["metadata"],
            "agent_scratchpad": format_to_openai_tool_messages(prompt_input["intermediate_steps"])
        })
        agent_invoke_start_time = time.time()
        output = agent.invoke(prompt_input)
        logger.info(f"agent.invoke took {time.time() - agent_invoke_start_time:.2f} seconds")
        logger.info(output)

        run = True
        while not isinstance(output, AgentFinish) and run:
            for selected_tool in output:
                logger.info("Tool call:     --->    " + selected_tool.log.strip())
                if isinstance(selected_tool, ToolAgentAction):
                    name = selected_tool.tool
                    tool_input = selected_tool.tool_input

                    if name == "execute_sql_query":
                        start_time = time.time()
                        tool_output = execute_sql_query_imp(settings, logger, db_conn_str, **tool_input)
                        elapsed_time = time.time() - start_time
                        logger.info(f"execute_sql_query_imp took {elapsed_time:.2f} seconds")

                    logger.info("Observation:   --->    " + str(tool_output))
                    prompt_input["intermediate_steps"].append((
                        # AgentAction(tool=name, tool_input=tool_input, log=selected_tool.log),
                        selected_tool, tool_output
                    ))

            testing_prompt = agent_prompt.format(**{
                "conversation": prompt_input["conversation"],
                "metadata": prompt_input["metadata"],
                "agent_scratchpad": format_to_openai_tool_messages(prompt_input["intermediate_steps"])
            })
            agent_invoke_start_time = time.time()
            output = agent.invoke(prompt_input)
            logger.info(f"agent.invoke took {time.time() - agent_invoke_start_time:.2f} seconds")
            logger.info(output)

            # run = False
        output = output.messages[0].content
        # logger.info("Final output:   --->    " + output)
        return output
    except Exception as e:
        logger.warning(f"Error in sql agent:\n{(str(e))}")
        return f"Error in sql agent:\n{str(e)}"


# # #### Testing Code ####
# from utils import get_settings, get_logger, get_db_connection
# settings = get_settings()
# logger = get_logger(settings)
# db_conn_str: str = get_db_connection(settings, logger)

# # # # #### Tools testing ####
# # output = execute_sql_query_imp(settings, logger, db_conn_str,"SELECT * FROM Products", limit=3)
# # print(output)
# # #
# # Sample conversation
# conversation = MessagesList()
# # Adding messages to the conversation
# conversation.add_message(Message(text="how many products we have", sender=Sender.USER))
# # conversation.add_message(Message(text="Sure, I'm here to help. What seems to be the problem?", sender=Sender.ASSISTANT))
# print(f"Agent Output:\n{sql_agent(settings, logger, db_conn_str, conversation)}")
