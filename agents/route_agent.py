import logging
import os
from pathlib import Path
from dynaconf import Dynaconf

# --- SPECIFIC IMPORTS ---
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
from langchain_core.tools import StructuredTool

# --- IMPORTING TOOLS ---
# Assuming websearch and memory are valid StructuredTools or Callables from your project
from agent_tools.memory import thread_memory_manager
from agent_tools.websearch import web_search_tool

# --- IMPORTING YOUR DB AGENT ---
from agents.db_agent import db_agent 

def router_agent(
    settings: Dynaconf,
    logger: logging.Logger,
    user_query: str
) -> str:
    """
    Main Router/Decision Agent.
    Role: Analyzes user intent and routes tasks to Web Search, Memory, or the DB Specialist.
    """
    try:
        # 1. Configure Environment
        os.environ["GROQ_API_KEY"] = settings.get("GROQ_API_KEY")
        
        # 2. Define the Wrapper for the DB Agent
        # We wrap the db_agent function so it matches the signature expected by the LLM tool (single string input)
        def query_db_specialist(query: str) -> str:
            """
            Input should be a specific question about data, records, or sql requirements.
            """
            logger.info(f"🔄 Routing to DB Agent with query: {query}")
            return db_agent(
                settings=settings,
                logger=logger,
                query_context=query
            )

        # Create the StructuredTool definition
        db_agent_tool = StructuredTool.from_function(
            func=query_db_specialist,
            name="db_specialist_agent",
            description="Use ONLY when the user asks about database records, SQL, internal data, or verifying specific user details."
        )

        # 3. Aggregate Tools
        # We combine your imported tools with our newly created sub-agent tool
        tools = [web_search_tool, thread_memory_manager, db_agent_tool]
        
        # Create a mapping for easy execution in the loop
        tool_map = {tool.name: tool for tool in tools}

        # 4. Configure LLM
        llm = ChatGroq(
            temperature=0,
            model_name="openai/gpt-oss-20", # Ensure this model name is valid in your Groq context
        )
        
        # Bind tools to LLM
        llm_with_tools = llm.bind_tools(tools)

        # 5. Load System Prompt
        try:
            prompt_path = Path("router_system_prompt.xml")
            if prompt_path.exists():
                system_prompt = prompt_path.read_text(encoding="utf-8")
            else:
                # Fallback if file missing
                system_prompt = "You are a helpful routing assistant. Use the db_specialist_agent for database queries."
        except Exception as e:
            logger.error(f"Error loading Router prompt: {str(e)}")
            system_prompt = "You are a helpful assistant."

        # 6. Define the Agent Chain
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = (
            {
                "input": lambda x: x["input"],
                "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
            }
            | prompt
            | llm_with_tools
            | OpenAIToolsAgentOutputParser()
        )

        # 7. Execution Loop (Best Practice Manual Loop)
        prompt_input = {
            "input": user_query,
            "intermediate_steps": []
        }

        # Initial Invocation
        output = agent.invoke(prompt_input)

        # Loop until AgentFinish is reached
        while not isinstance(output, AgentFinish):
            
            # Iterate through actions requested by the LLM
            for action in output:
                if not isinstance(action, ToolAgentAction):
                    continue

                tool_name = action.tool
                tool_input = action.tool_input
                
                logger.info(f"🤖 Router executing tool: {tool_name}")

                # Execute the specific tool
                if tool_name in tool_map:
                    try:
                        selected_tool = tool_map[tool_name]
                        # Handling input: if tool_input is a dict, unpack it, else pass directly
                        if isinstance(tool_input, dict):
                            tool_output = selected_tool.run(tool_input)
                        else:
                            tool_output = selected_tool.run(tool_input)
                    except Exception as tool_err:
                        tool_output = f"Error executing tool {tool_name}: {str(tool_err)}"
                        logger.error(tool_output)
                else:
                    tool_output = f"Error: Unknown tool '{tool_name}'"

                # Append result to intermediate steps
                prompt_input["intermediate_steps"].append((action, tool_output))

            # Re-invoke the agent with new history
            output = agent.invoke(prompt_input)

        # 8. Return Final Output
        return output.return_values["output"]

    except Exception as e:
        logger.error("ROUTER AGENT FAILURE", exc_info=True)
        return "I encountered a critical error while processing your request."