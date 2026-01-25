import logging
import os
from pathlib import Path
from dynaconf import Dynaconf
from langchain_core.agents import AgentFinish
from langchain.agents.output_parsers.tools import ToolAgentAction
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents.format_scratchpad.openai_tools import (
    format_to_openai_tool_messages,
)
from langchain.agents.output_parsers.openai_tools import (
    OpenAIToolsAgentOutputParser,
)

# Internal Imports
from data_models.data_models import MessagesList
from agent_tools.sql import (
    execute_sql_query,
    execute_sql_query_imp
)

def get_tables_metadata(settings: Dynaconf):
    """Reads and returns the table metadata from the specified file."""
    try:
        with open(settings.get("METADATA_PATH"), "r", encoding="utf-8") as file:
            metadata = file.read()
        return metadata
    except Exception as e:
        return f"Error loading metadata: {str(e)}"

def db_agent(
    settings: Dynaconf,
    logger: logging.Logger,
    db_conn_str: str,
    query_context: str,  # The specific user query forwarded by the Router
    thread_id: str
) -> str:
    """
    Specialized SQL/DB Agent.
    Role: Receives a task from the Router, executes SQL against the DB, and returns the answer.
    """
    try:
        # 1. Prepare Context
        metadata = get_tables_metadata(settings)
        
        # 2. Initialize LLM
        # Using a model capable of complex SQL generation
        os.environ["GROQ_API_KEY"] = settings.get("GROQ_API_KEY")
        llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)
        
        # 3. Define Tools (ONLY SQL Related)
        tools = [execute_sql_query]

        try:
        # Read the DB Agent XML file
            prompt_path = Path("db_system_prompt.xml")
        
            if prompt_path.exists():
                xml_template = prompt_path.read_text(encoding="utf-8")

                system_prompt = xml_template.replace("{metadata}", metadata)
            else:
                logger.error("db_system_prompt.xml not found!")
                return "System Error: Configuration file missing."

        except Exception as e:
            logger.error(f"Error loading DB prompt: {str(e)}")
            return "System Error: Failed to load agent configuration."

    # ---------------------------------------------------------
    
        agent_prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        llm_with_tools = llm.bind_tools(tools)

        agent = (
            {
                "input": lambda x: x["input"],
                "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
            }
            | agent_prompt
            | llm_with_tools
            | OpenAIToolsAgentOutputParser()
        )

        # 5. Execution Loop
        prompt_input = {
            "input": query_context,
            "intermediate_steps": []
        }
        
        output = agent.invoke(prompt_input)

        while not isinstance(output, AgentFinish):
            for action in output:
                if not isinstance(action, ToolAgentAction):
                    continue

                tool_name = action.tool
                tool_input = action.tool_input
                
                logger.info(f"💾 DBAgent executing: {tool_name}")

                if tool_name == "execute_sql_query":
                    safe_input = tool_input.copy() if isinstance(tool_input, dict) else {}
                    
                    # Ensure query exists
                    if "query" not in safe_input:
                        safe_input["query"] = query_context

                    # Execute the implementation directly
                    tool_output = execute_sql_query_imp(
                        settings=settings,
                        logger=logger,
                        conn_str=db_conn_str,
                        **safe_input
                   )
                else:
                    tool_output = f"Error: DBAgent only supports SQL tools. Unknown tool: {tool_name}"

                prompt_input["intermediate_steps"].append((action, tool_output))

            output = agent.invoke(prompt_input)

        return output.return_values["output"]

    except Exception as e:
        logger.error("DB AGENT FAILURE", exc_info=True)
        return "I encountered an error while trying to query the database."