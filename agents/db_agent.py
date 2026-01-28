import logging
import os
from pathlib import Path
from dynaconf import Dynaconf
from langchain_core.agents import AgentFinish
from langchain.agents.output_parsers.tools import ToolAgentAction
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents.format_scratchpad.openai_tools import format_to_openai_tool_messages
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser

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


def sql_agent(
        settings: Dynaconf,
        logger: logging.Logger,
        db_conn_str: str,
        conversation: MessagesList,
) -> str:
    """
    Pure SQL agent. No routing, no web search.
    Only capability: Generate and execute SQL based on conversation and metadata.
    """
    try:

        conv_text = str(conversation).strip()
        normalized_user_message = " ".join(conv_text.split())

        metadata = get_tables_metadata(settings)

        os.environ["GROQ_API_KEY"] = settings.get("GROQ_API_KEY")

        llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)

        tools = [execute_sql_query]

        try:
            system_prompt = Path("db_system_prompt.xml").read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error("db_system_prompt.xml not found.")
            return "System configuration error: Prompt file missing."

        user_template = "Conversation: {conversation}"

        agent_prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_template), # LangChain safely injects vars here
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        llm_with_tools = llm.bind_tools(tools)

        agent = (
                {
                    "conversation": lambda x: str(x["conversation"]),
                    "metadata": lambda x: x["metadata"],
                    "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
                }
                | agent_prompt
                | llm_with_tools
                | OpenAIToolsAgentOutputParser()
        )

        prompt_input = {
            "conversation": conversation,
            "metadata": metadata,
            "intermediate_steps": []
        }

        output = agent.invoke(prompt_input)

        while not isinstance(output, AgentFinish):
            for action in output:
                if not isinstance(action, ToolAgentAction):
                    continue

                tool_name = action.tool
                tool_input = action.tool_input

                logger.info(f"🛠️ Agent executing: {tool_name}")

                if tool_name == "execute_sql_query":
                    safe_input = tool_input.copy() if isinstance(tool_input, dict) else {}

                    if "query" not in safe_input:
                        safe_input["query"] = normalized_user_message

                    tool_output = execute_sql_query_imp(
                        settings=settings,
                        logger=logger,
                        conn_str=db_conn_str,
                        **safe_input
                    )
                else:
                    tool_output = {"status": "error",
                                   "message": f"This agent is restricted to SQL operations only. Unknown tool: {tool_name}"}

                prompt_input["intermediate_steps"].append((action, tool_output))

            output = agent.invoke(prompt_input)

        return output.return_values["output"]

    except Exception as e:
        logger.error("SQL AGENT FAILURE", exc_info=True)
        if "Parsing failed" in str(e):
            return "I retrieved the data successfully but couldn't format the answer correctly. Please try again."

        return "I encountered an internal system error while processing your request. Please try again."