import logging
import os
from pathlib import Path
from dynaconf import Dynaconf
from groq import Groq

# Internal Imports
from data_models.data_models import MessagesList
from agent_tools.websearch import web_search_tool
from agent_tools.memory import thread_memory_manager

# Import the DBAgent
from agents import db_agent

logger = logging.getLogger(__name__)

def router_agent(
    settings: Dynaconf,
    logger: logging.Logger,

    conversation: MessagesList,
    thread_id: str
) -> str:
    """
    Router Agent (Orchestrator).
    Capabilities:
    1. Manages Thread Memory (Read/Write).
    2. Classifies Intent (DB vs Web vs Reset).
    3. Executes Web Search Tool directly.
    4. Delegates DB tasks to the 'db_agent'.
    """
    try:
        # Normalize Input
        conv_text = str(conversation).strip()
        user_message = " ".join(conv_text.split())[-2000:] # Take last portion for context
        
        GROQ_API_KEY = settings.get("GROQ_API_KEY")
        if not GROQ_API_KEY:
            return "Configuration Error: GROQ_API_KEY missing."

        client = Groq(api_key=GROQ_API_KEY)
        
        try:
            prompt_path = Path("router_system_prompt.xml")
            if prompt_path.exists():
                # We just read the text. We do NOT need to inject metadata anymore.
                system_instruction = prompt_path.read_text(encoding="utf-8")
            else:
                system_instruction = "You are a query router. Options: [sql_db, web_search, reset_memory]."

        except Exception as e:
            logger.error(f"Error loading Router prompt: {str(e)}")
            return "System Error: Internal Error in Router."

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"User Query: \"{user_message}\""}
        ]

        response = client.chat.completions.create(
            model="openai/gpt-oss-20b", # Smaller, faster model for routing
            messages=messages,
            temperature=0.0,
            max_tokens=10
        )

        decision = response.choices[0].message.content.strip().lower()
        logger.info(f"🧠 Router Decided: {decision}")

        final_response = ""

        # -------------------------------
        # 3. Routing & Execution
        # -------------------------------
        
        # CASE A: Memory Reset
        if "reset" in decision or "memory" in decision:
            thread_memory_manager.invoke({"thread_id": thread_id, "action": "reset"})
            final_response = "I have reset the conversation memory. We can start fresh."

        # CASE B: Web Search (Router handles directly)
        elif "web" in decision or "search" in decision:
            logger.info("🌍 Delegating to Web Search Tool")
            # Using the web_search_tool directly as requested
            search_result = web_search_tool.invoke(user_message)
            
            # Synthesize answer (Optional: You can return raw result or summarize)
            # For simplicity, returning the search result, or you could add a small summarization call here.
            final_response = f"Here is what I found on the web:\n{search_result}"

        # CASE C: Database Query (Delegate to DBAgent)
        elif "sql" in decision or "db" in decision or "database" in decision:
            logger.info("🗄️ Delegating to DBAgent")
            final_response = db_agent(
                settings=settings,
                logger=logger,
                db_conn_str=str,
                query_context=user_message,
                thread_id=thread_id
            )
            
        # CASE D: Fallback (Default to DB if unsure, or Web)
        else:
            # Fallback logic: Default to DBAgent
            final_response = db_agent(
                settings=settings,
                logger=logger,
                query_context=user_message,
                thread_id=thread_id
            )

        # -------------------------------
        # 4. Memory Management (WRITE)
        # -------------------------------
        thread_memory_manager.invoke({
            "thread_id": thread_id, 
            "action": "write", 
            "content": f"User: {user_message}\nAI: {final_response}"
        })

        return final_response

    except Exception as e:
        logger.error("ROUTER AGENT FAILURE", exc_info=True)
        return "System Error: Unable to process request in Router."