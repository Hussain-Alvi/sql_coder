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


def read_text_file(logger: logging.getLogger, file_path):
    """
    Reads the content of a text file.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            file_content = file.read()
        return file_content
    except FileNotFoundError:
        logger.error(f"Error: The file was not found at path: '{file_path}'")
        return None
    except Exception as e:
        logger.error(f"⚠An unexpected error occurred while reading the file: {e}")
        return None



def sql_agent(settings: Dynaconf, logger: logging.getLogger, db_conn_str: str, conversation: MessagesList) -> str:
    """
    The main function for the SQL agent.
    """
    try:
        start_time = time.perf_counter()
        os.environ["GROQ_API_KEY"] = settings.get("GROQ_API_KEY")
        current_date = date.today().isoformat()
        bank_islamic_metadata = read_text_file(logger,  settings.get("BANK_ISLAMIC_METADATA"))

        # "gpt-5" | "gpt-4.1" | "gpt-3.5-turbo" | "gpt-4-0125-preview"
        # llm = ChatOpenAI(model="gpt-4.1", temperature=1)
        # "meta-llama/llama-4-maverick-17b-128e-instruct" |  "openai/gpt-oss-120b"
        llm = ChatGroq(model_name="openai/gpt-oss-120b")

        tools = [
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
                    "bank_islamic_metadata": lambda x: x["bank_islamic_metadata"],
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
            "bank_islamic_metadata": bank_islamic_metadata,
            "intermediate_steps": []
        }
        # agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        # output = agent_executor.invoke(prompt_input)
        # logger.info(output)

        testing_prompt = agent_prompt.format(**{
            "conversation": prompt_input["conversation"],
            "bank_islamic_metadata": prompt_input["bank_islamic_metadata"],
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
                    # if name == "get_table_info":
                    #     tool_output = get_table_info_imp(settings, logger, db_conn_str, **tool_input)
                    # else:
                    #     logger.warning(f"Unknown tool: {name}")
                    #     tool_output = f"Unknown tool: {name}"

                    # logger.info("Observation:   --->    " + str(tool_output))
                    # prompt_input["intermediate_steps"].append((
                    #     # AgentAction(tool=name, tool_input=tool_input, log=selected_tool.log),
                    #     selected_tool, tool_output
                    # ))

            testing_prompt = agent_prompt.format(**{
                "conversation": prompt_input["conversation"],
                "bank_islamic_metadata": prompt_input["bank_islamic_metadata"],
                "current_date": prompt_input["current_date"],
                "agent_scratchpad": format_to_openai_tool_messages(prompt_input["intermediate_steps"])
            })
            output = agent.invoke(prompt_input)
            logger.info(output)

            # run = False
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
#
# if __name__ == '__main__':
#     settings = get_settings()
#     logger = get_logger(settings)
#     db_conn_str: str = get_db_connection(settings, logger)
#
#     # Sample conversation
#     conversation = MessagesList()
#     conversation.add_message(Message(text="how many active products we have", sender=Sender.USER))
#     print(f"Agent Output:\n{sql_agent(settings, logger, db_conn_str, conversation)}")
