# import logging
# import os
# from pathlib import Path
# from dynaconf import Dynaconf
# from langchain_core.agents import AgentFinish
# from langchain.agents.output_parsers.tools import ToolAgentAction
# from langchain_groq import ChatGroq
# from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
# from langchain.agents.format_scratchpad.openai_tools import (
#     format_to_openai_tool_messages,
# )
# from langchain.agents.output_parsers.openai_tools import (
#     OpenAIToolsAgentOutputParser,
# )

# # Internal Imports
# from data_models.data_models import MessagesList
# from agent_tools.decision import decide_tool
# from agent_tools.websearch import web_search_tool
# from agent_tools.memory import thread_memory_manager
# from agent_tools.sql import (
#     execute_sql_query,
#     execute_sql_query_imp
# )



# def get_tables_metadata(settings: Dynaconf):
#     """Reads and returns the table metadata from the specified file."""
#     try:
#         with open(settings.get("METADATA_PATH"), "r", encoding="utf-8") as file:
#             metadata = file.read()
#         return metadata
#     except Exception as e:
#         return f"Error loading metadata: {str(e)}"

# def sql_agent(
#     settings: Dynaconf,
#     logger: logging.Logger,
#     db_conn_str: str,
#     conversation: MessagesList,
#     thread_id: str
# ) -> str:
#     """
#     SQL agent with Groq compound model deciding tool immediately.
#     """
#     try:
#         # Normalize conversation
#         conv_text = str(conversation).strip()
#         normalized_user_message = " ".join(conv_text.split())

#         # -------------------------------
#         # 1. Memory Management (Read/Write)
#         # -------------------------------
#         thread_memory_manager.invoke({"thread_id": thread_id, "action": "read"})
#         thread_memory_manager.invoke({"thread_id": thread_id, "action": "write", "content": str(conversation)})

#         # -------------------------------
#         # 2. Prepare Context
#         # -------------------------------
#         metadata = get_tables_metadata(settings)

#         # -------------------------------
#         # 3. Initialize LLM & Agent
#         # -------------------------------
#         os.environ["GROQ_API_KEY"] = settings.get("GROQ_API_KEY")
        
#         # Initialize Groq Model
#         llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)
        
#         tools = [execute_sql_query, thread_memory_manager, web_search_tool, decide_tool]

#         # Load System Prompt
#         try:
#             system_prompt = Path("system_prompt.xml").read_text(encoding="utf-8")
#         except FileNotFoundError:
#             logger.error("system_prompt.xml not found.")
#             return "System configuration error: Prompt file missing."
        
#         user_prompt = f"Session ID: {thread_id}\nConversation:\n{conversation}"

#         agent_prompt = ChatPromptTemplate.from_messages([
#             ("system", system_prompt),
#             ("user", user_prompt),
#             MessagesPlaceholder(variable_name="agent_scratchpad")
#         ])

#         llm_with_tools = llm.bind_tools(tools)

#         agent = (
#             {
#                 "conversation": lambda x: x["conversation"],
#                 "thread_id": lambda x: x["thread_id"],
#                 "metadata": lambda x: x["metadata"],
#                 "agent_scratchpad": lambda x: format_to_openai_tool_messages(x["intermediate_steps"]),
#             }
#             | agent_prompt
#             | llm_with_tools
#             | OpenAIToolsAgentOutputParser()
#         )

#         # -------------------------------
#         # 4. ReAct Execution Loop
#         # -------------------------------
#         prompt_input = {
#             "conversation": conversation,
#             "thread_id": thread_id,
#             "metadata": metadata,
#             "intermediate_steps": []
#         }
        
#         # Initial Agent Call
#         output = agent.invoke(prompt_input)

#         while not isinstance(output, AgentFinish):
#             for action in output:
#                 if not isinstance(action, ToolAgentAction):
#                     continue

#                 tool_name = action.tool
#                 tool_input = action.tool_input

#                 # ----------------------------------------------
#                 # LOGIC: Immediate Groq-driven tool decision
#                 # ----------------------------------------------
#                 if tool_name == "decide_tool":
#                     # Create input for the router
#                     router_input = {
#                         "query": normalized_user_message, 
#                         "metadata": metadata
#                     }
                    
#                     # FIX: Use .invoke() instead of calling it like a function
#                     chosen_tool = decide_tool.invoke(router_input)
                    
#                     logger.info(f"🧠 Groq Router decided: {chosen_tool}")
#                 else:
#                     chosen_tool = tool_name

#                 logger.info(f"🛠️ ReAct executing: {chosen_tool}")

#                 # -------------------------------
#                 # Tool Execution
#                 # -------------------------------
#                 if chosen_tool == "execute_sql_query":
#                     safe_input = tool_input.copy() if isinstance(tool_input, dict) else {}
                    
#                     # CLEANUP: Remove arguments that execute_sql_query_imp does not accept
#                     safe_input.pop("thread_id", None) 
#                     safe_input.pop("metadata", None)  # <--- FIX: Remove metadata argument
                    
#                     # Ensure query arg exists (fallback to user message if missing)
#                     if "query" not in safe_input:
#                         safe_input["query"] = normalized_user_message

#                     tool_output = execute_sql_query_imp(
#                         settings=settings,
#                         logger=logger,
#                         conn_str=db_conn_str,
#                         **safe_input
#                    )

#                 elif chosen_tool == "web_search":
#                     # Handle input format differences
#                     query_arg = tool_input.get("query", normalized_user_message) if isinstance(tool_input, dict) else normalized_user_message
#                     tool_output = web_search_tool.invoke(query_arg)
                
#                 elif chosen_tool == "reset_memory":
#                     # Logic for memory reset decision
#                     thread_memory_manager.invoke({"thread_id": thread_id, "action": "reset"})
#                     tool_output = "Memory has been reset successfully. Please start a new topic."
#                     logger.info(f"🧠 Thread memory reset for ID: {thread_id}")

#                 elif chosen_tool == "thread_memory_manager":
#                     final_input = tool_input.copy() if isinstance(tool_input, dict) else {}
#                     final_input["thread_id"] = thread_id
#                     tool_output = thread_memory_manager.invoke(final_input)
                
#                 else:
#                     tool_output = {"status": "error", "message": f"Unknown tool: {chosen_tool}"}

#                 # Append intermediate step
#                 prompt_input["intermediate_steps"].append((action, tool_output))

#             # Run agent again with new observations
#             output = agent.invoke(prompt_input)

#         return output.return_values["output"]

#     except Exception as e:
#         logger.error("SQL AGENT FAILURE", exc_info=True)
#         # Gentle error handling
#         if "Parsing failed" in str(e):
#             return "I retrieved the data successfully but couldn't format the answer correctly. Please try again."
        
#         return "I encountered an internal system error while processing your request. Please try again."