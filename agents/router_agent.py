import logging
import os
from pathlib import Path
from dynaconf import Dynaconf
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.agents import AgentFinish
from langchain.agents.output_parsers.tools import ToolAgentAction
from langchain.agents.format_scratchpad.openai_tools import (
    format_to_openai_tool_messages,
)
from langchain.agents.output_parsers.openai_tools import (
    OpenAIToolsAgentOutputParser,
)
from langchain_core.tools import tool

# Internal imports
from agents.db_agent import sql_agent
from agent_tools.websearch import web_search_tool
from agent_tools.memory import thread_memory_manager
from data_models.data_models import MessagesList

logger = logging.getLogger(__name__)


def _get_groq_api_key(settings: Dynaconf = None) -> str | None:
    if settings:
        key = settings.get("GROQ_API_KEY")
        if key:
            return str(key)
    return os.getenv("GROQ_API_KEY")


def master_router_agent(
        settings: Dynaconf,
        db_conn_str: str,
        conversation: MessagesList,
        thread_id: str
) -> str:
    """
    Orchestrator Agent:
    Uses LangChain Tool Calling to decide whether to:
    1. Delegate to SQL Agent
    2. Delegate to Web Search
    3. Manage Memory
    4. Respond directly (General Chat)
    """
    try:
        api_key = _get_groq_api_key(settings)
        llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0.0, api_key=api_key)

        @tool("ask_database")
        def call_sql_agent(query: str) -> str:
            """
            Use this tool for questions about internal data, users, metrics,
            tables, or any data stored in the database.
            Input should be the specific question for the database.
            """
            logger.info(f"🔄 Routing to SQL Agent: {query}")

            sub_conversation = [{"role": "user", "content": query}]

            return sql_agent(
                settings=settings,
                logger=logger,
                db_conn_str=db_conn_str,
                conversation=sub_conversation,
                thread_id=thread_id
            )

        @tool("web_search")
        def call_web_search(query: str) -> str:
            """
            Use this tool for questions about current events, public news,
            or information not contained in the internal database.
            """
            logger.info(f"🔄 Routing to Web Search: {query}")
            return web_search_tool.invoke(query)

        @tool("reset_memory")
        def call_memory_reset(confirm: str = "yes") -> str:
            """
            Use this tool if the user specifically asks to 'forget' context,
            'reset' the chat, or 'clear' memory.
            """
            logger.info("🔄 Routing to Memory Manager")
            thread_memory_manager.invoke({"thread_id": thread_id, "action": "reset"})
            return "Memory has been reset successfully."

        tools = [call_sql_agent, call_web_search, call_memory_reset]

        try:
            system_instruction = Path("router_system_prompt.xml").read_text(encoding="utf-8")
        except FileNotFoundError:
            return "System configuration error: Prompt file missing."

        agent_prompt = ChatPromptTemplate.from_messages([
            ("system", system_instruction),
            ("user", "Session ID: {thread_id}\nConversation:\n{conversation}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        llm_with_tools = llm.bind_tools(tools)

        agent = (
                {
                    "conversation": lambda x: x["conversation"],
                    "thread_id": lambda x: x["thread_id"],
                    "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
                }
                | agent_prompt
                | llm_with_tools
                | OpenAIToolsAgentOutputParser()
        )

        prompt_input = {
            "conversation": str(conversation),  # Convert to str for the context window
            "thread_id": thread_id,
            "intermediate_steps": []
        }

        output = agent.invoke(prompt_input)

        while not isinstance(output, AgentFinish):

            for action in output:
                if not isinstance(action, ToolAgentAction):
                    continue

                tool_name = action.tool
                tool_input = action.tool_input

                logger.info(f"🛠️ Router executing tool: {tool_name}")

                # Map tool names to the actual function calls
                tool_result = None

                try:
                    if tool_name == "ask_database":
                        # Extract query argument safely
                        q = tool_input.get("query") if isinstance(tool_input, dict) else tool_input
                        tool_result = call_sql_agent.invoke(q)

                    elif tool_name == "web_search":
                        q = tool_input.get("query") if isinstance(tool_input, dict) else tool_input
                        tool_result = call_web_search.invoke(q)

                    elif tool_name == "reset_memory":
                        tool_result = call_memory_reset.invoke("yes")


                except Exception as tool_err:
                    logger.error(f"Tool execution failed: {tool_err}")
                    tool_result = f"Error executing tool {tool_name}: {str(tool_err)}"

                prompt_input["intermediate_steps"].append((action, tool_result))

            output = agent.invoke(prompt_input)

        return output.return_values["output"]

    except Exception as e:
        logger.error("ROUTER AGENT FAILURE", exc_info=True)
        return "I encountered an internal system error while routing your request. Please try again."