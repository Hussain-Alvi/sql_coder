import logging
import os
from pathlib import Path
from dynaconf import Dynaconf
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.agents import AgentFinish
from langchain.agents.output_parsers.tools import ToolAgentAction
from langchain.agents.format_scratchpad.openai_tools import format_to_openai_tool_messages
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser

# Internal imports
from data_models.data_models import MessagesList
from agent_tools.invoker_tools import get_router_tools

logger = logging.getLogger(__name__)

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
        os.environ["GROQ_API_KEY"] = settings.get("GROQ_API_KEY")
        llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0.0)

        tools = get_router_tools(
            settings=settings,
            db_conn_str=db_conn_str,
            conversation=conversation,
            thread_id=thread_id
        )

        tool_map = {t.name: t for t in tools}

        try:
            system_instruction = Path("router_system_prompt.xml").read_text(encoding="utf-8")
        except FileNotFoundError:
            return "System configuration error: Prompt file missing."

        agent_prompt = ChatPromptTemplate.from_messages([
            ("system", system_instruction),
            ("user", "Conversation: {conversation}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        llm_with_tools = llm.bind_tools(tools)

        agent = (
                {
                    "conversation": lambda x: x["conversation"],
                    "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
                }
                | agent_prompt
                | llm_with_tools
                | OpenAIToolsAgentOutputParser()
        )

        prompt_input = {
            "conversation": str(conversation),
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

                try:
                    if tool_name in tool_map:
                        target_tool = tool_map[tool_name]

                        q = tool_input.get("query") if isinstance(tool_input, dict) and "query" in tool_input else tool_input

                        if tool_name == "reset_memory":
                            tool_result = target_tool.invoke("yes")
                            return str(tool_result)

                        tool_result = target_tool.invoke(q)
                    else:
                        tool_result = f"Error: Tool '{tool_name}' not found in configuration."

                except Exception as tool_err:
                    logger.error(f"Tool execution failed: {tool_err}")
                    tool_result = f"Error executing tool {tool_name}: {str(tool_err)}"

                prompt_input["intermediate_steps"].append((action, tool_result))

            output = agent.invoke(prompt_input)

        return output.return_values["output"]

    except Exception as e:
        logger.error("ROUTER AGENT FAILURE", exc_info=True)
        return "I encountered an internal system error while routing your request. Please try again."