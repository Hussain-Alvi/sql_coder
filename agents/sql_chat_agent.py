"""
Langchain agent of SQL Assistant.
"""
import logging
import os
import time
from datetime import date
from pathlib import Path

from dynaconf import Dynaconf
from langchain.agents.output_parsers.tools import ToolAgentAction
from langchain_groq import ChatGroq
from langchain_core.agents import AgentFinish
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents.format_scratchpad.openai_tools import (format_to_openai_tool_messages)
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser

from data_validations.data_models import MessagesList
from included_tables.tables import TABLE_LIST
from agent_tools.tools import (
    get_table_info,
    execute_sql_query,
    get_table_info_imp,
    execute_sql_query_imp,
)

today = date.today()
current_date = today.isoformat()


def sql_agent(settings: Dynaconf, logger: logging.getLogger, db_conn_str: str, conversation: MessagesList) -> str:
    """
    The main function for the SQL agent.
    """
    start_time = time.perf_counter()
        # Early exit for greetings or non-SQL input
    if (
        isinstance(conversation, str)
        and conversation.strip().lower() in ["hi", "hello", "hey", "good morning", "good evening"]
    ) or (
        hasattr(conversation, "messages") 
        and len(conversation.messages) == 1 
        and conversation.messages[0].text.strip().lower() in ["hi", "hello", "hey"]
    ):
        logger.info("Received greeting, skipping SQL prompt.")
        return "👋 Hi there! I can help you explore or query the database. Try asking things like 'Show top 5 products by price'."

    try:
        os.environ["GROQ_API_KEY"] = settings.get("GROQ_API_KEY")
        global TABLE_LIST, current_date

        llm = ChatGroq(model_name="meta-llama/llama-4-maverick-17b-128e-instruct")

        tools = [
            get_table_info,
            execute_sql_query
        ]

        system_prompt = Path("system_prompt/system_prompt.txt").read_text(encoding="utf-8")

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
        )

        prompt_input = {
            "query": "",
            "table_names": "",
            "conversation": conversation,
            "current_date": current_date,
            "table_list": "\n".join(TABLE_LIST),
            "intermediate_steps": []
        }


        output = agent.invoke(prompt_input)
        logger.info(output)

        while not isinstance(output, AgentFinish):
            for selected_tool in output:
                logger.info("Tool call:     --->    " + selected_tool.log.strip())
                if isinstance(selected_tool, ToolAgentAction):
                    name = selected_tool.tool
                    tool_input = selected_tool.tool_input

                    tool_output = ""
                    if name == "get_table_info":
                        tool_output = get_table_info_imp(settings, logger, db_conn_str, **tool_input)
                    elif name == "execute_sql_query":
                        tool_output = execute_sql_query_imp(settings, logger, db_conn_str, **tool_input)
                    else:
                        logger.warning(f"Unknown tool: {name}")
                        tool_output = f"Unknown tool: {name}"

                    logger.info("Observation:   --->    " + str(tool_output))
                    prompt_input["intermediate_steps"].append((
                        selected_tool, tool_output
                    ))

            output = agent.invoke(prompt_input)
            logger.info(output)

        final_output = output.messages[0].content
        end_time = time.perf_counter()
        logger.info(f"SQL Agent completed in {end_time - start_time:.2f}s")
        return final_output

    except Exception as e:
        logger.warning(f"Error in sql agent:\n{(str(e))}")
        return f"Error in sql agent:\n{str(e)}"

# # # #### Testing Code ####
# from utilities.utils import get_settings, get_logger, get_db_connection
# from data_validations.data_models import Message, Sender

# if __name__ == '__main__':
#     settings = get_settings()
#     logger = get_logger(settings)
#     db_conn_str: str = get_db_connection(settings, logger)

#     # Sample conversation
#     conversation = MessagesList()
#     conversation.add_message(Message(text="how many active products we have", sender=Sender.USER))
#     print(f"Agent Output:\n{sql_agent(settings, logger, db_conn_str, conversation)}")