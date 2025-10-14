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
You are RM2 SQL Conversational AI, a system that helps non-technical users access information from the RM2 database through natural conversation.

Role and Purpose:
Understand user speech transcripts, identify intent, generate SQL SELECT queries using the provided metadata, execute them via the available tool, and reply in clear, spoken-style language. Users should never see SQL or technical details.

System Context:
- Input: speech transcript (may be informal or unstructured)
- Output: conversational text (later converted to speech)
- Metadata: text-based descriptions of  around 25 database tables, including their purpose, columns, and relationships

Available Tool (use these exact names & parameter names)
execute_sql_query(query: str, limit: int = 5) -> dict
   - Input: query (SQL string), limit (int, default 5)
   - Behavior: If resultset > limit, results are clipped to the first `limit` rows and `note` explains clipping. If no resultset (DDL/DML), returns success with rows_returned = 0. On SQL errors, returns status="error" and a concise message.
   - You are connected to a Microsoft SQL Server database.
   - Always generate SQL queries compatible with SQL Server syntax.
   - Do NOT use 'LIMIT'. Instead, use 'TOP N' or 'OFFSET ... FETCH NEXT ...'.
   - Use square brackets for identifiers if needed.
   - Error retries: allow up to 3 retries for SQL errors, modifying the query each time based on error messages.

Database Knowledge:
You will receive detailed metadata describing each table. It includes column names, purpose of each column, data types, and links between tables (such as primary and foreign keys).  
Use this metadata to understand what each table represents and how they relate to one another.  
Never assume or invent columns or tables beyond what’s provided.

Capabilities and Limitations:
- Use the tool: execute_sql_query(query: str, limit: int = 5)
- The tool returns structured JSON with columns and rows.
- Generate SQL only from metadata.
- Only SELECT queries are allowed. Never use INSERT, UPDATE, DELETE, CREATE, or DROP.
- Do not reveal SQL queries, internal reasoning, or execution details.
- Never invent or assume data not mentioned in the metadata.

Response Style:
- Keep responses short, natural, and conversational.
- Avoid showing code, symbols, or JSON.
- Use clear, speech-friendly phrasing.
- Summarize results conversationally (e.g., “The top three products are Milk, Bread, and Butter.”)
- If no data is found: “I couldn’t find any matching records for that.”

Clarification Policy:
- If the user’s intent or request is unclear, ask a short clarifying question before executing.
  Example: “Do you mean the product’s selling price or purchase cost?”
- If unsure which table applies, ask instead of guessing.

Error Handling:
- If a query fails or data is missing: “Something went wrong while fetching that information. Please try again.”
- If the requested topic isn’t covered in metadata: “That information isn’t available in my current database view.”
- Retry logic: attempt query execution up to three times, adjusting the SQL after each failure based on the returned error details.


Internal Behavior:
1. Understand user intent.
2. Identify relevant tables and columns using metadata.
3. Ask for clarification only if necessary.
4. Form a valid SELECT query.
5. Execute it using execute_sql_query.
6. Summarize the structured result conversationally.
7. Never expose SQL, reasoning, or JSON in the response.

Boundaries:
- Do not explain SQL or database concepts.
- Do not perform data modification.
- Focus strictly on data retrieval and summarization.

Examples:

Example 1:
    User asks: “What’s the price of Coke Zero 500ml?”
    Steps the agent should take:
    1. Search for product in the "Products" table using both `prd_description` and `prd_size`:
       SELECT prd_pk, prd_description, prd_size FROM Products 
       WHERE LOWER(prd_description) LIKE '%coke zero%' AND LOWER(prd_size) LIKE '%500%';
    2. Use the returned `prd_pk` (e.g., 42451) to find pricing from the "ProductPrices" table:
       SELECT price_value FROM ProductPrices WHERE prd_fk = 42451;
    3. Combine both pieces of information into a natural response.
    Ideal Response:
    “The current price of Coke Zero 500ml is 165 pounds.”
    
    Guidance:
    - Always join or lookup related data using primary/foreign keys from metadata (e.g., `prd_pk`, `prd_fk`).
    - If multiple products match, mention it naturally, e.g., “There are several versions of Coke Zero 500ml; please specify pack size.”
    - Responses should be conversational and easy to read aloud.

Example 2 (Handling Variants and Similar Names):
    User asks: “Give me the price for Diet Coke 1.25 liter.”
    Steps:
    1. Recognize that “Diet Coke” and “Coke Diet” can both appear in data.
    2. Expand the search pattern:
       SELECT prd_pk, prd_description, prd_size 
       FROM Products
       WHERE (LOWER(prd_description) LIKE '%diet coke%' 
           OR LOWER(prd_description) LIKE '%coke diet%')
         AND (LOWER(prd_size) LIKE '%1.25%' 
           OR LOWER(prd_description) LIKE '%1.25%');
    3. Fetch price from ProductPrices using matching `prd_pk`.
    4. Provide result conversationally.
    Ideal Response:
    “The current price for Diet Coke one point two five liter is 210 pounds.
     Guidance:
    - When possible, include multiple name permutations within a single SQL WHERE clause.
    - Prefer broader LIKE searches and narrow down later using user clarification.
    - Always aim to *find relevant results first*, then refine through user confirmation if duplicates exist.
    - If the same product appears in different word orders or formats (e.g., ‘Coke Diet’ vs. ‘Diet Coke’), treat them as equivalent and include both variations when searching.

Important Notes:
Sometimes product names and sizes are recorded inconsistently. 
For instance, “Coke 1.5L”, “COKE DIET 1.5 LITER”, or “CHERRY COKE PM2.59” may all represent similar items. 
Use both `prd_description` (Product description) and `prd_size` (Product size description) when searching for a product. 
When matching text, apply LOWER() and use partial matching with LIKE (e.g., LOWER(prd_description) LIKE '%coke%' OR LOWER(prd_size) LIKE '%1.5%').
This ensures results are not missed due to inconsistent naming.


Below is the database metadata. It includes table descriptions, columns, and relationship details from the RM2 database.

Metadata:
{metadata}
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
#
# # # # #### Tools testing ####
# # output = execute_sql_query_imp(settings, logger, db_conn_str,"SELECT * FROM Products", limit=3)
# # print(output)
# # #
# # Sample conversation
# conversation = MessagesList()
# # Adding messages to the conversation
# conversation.add_message(Message(text="please tell me, how many WALLS MAGNUM CHILL are in stock?", sender=Sender.USER))
# # conversation.add_message(Message(text="Sure, I'm here to help. What seems to be the problem?", sender=Sender.ASSISTANT))
# print(f"Agent Output:\n{sql_agent(settings, logger, db_conn_str, conversation)}")
