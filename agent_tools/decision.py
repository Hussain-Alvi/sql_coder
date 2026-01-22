# tools.py

import logging
from dynaconf import Dynaconf
from langchain.tools import tool
from pydantic import BaseModel, Field

from groq import Groq
import os
from pathlib import Path

logger = logging.getLogger("tools")
        
logger = logging.getLogger(__name__)

try:
    from dynaconf import Dynaconf
    settings = Dynaconf(
        settings_files=['settings.toml', '.secrets.toml'],
        environments=True,
        load_dotenv=True,
    )
    GROQ_API_KEY = settings.get("GROQ_API_KEY")
except ImportError:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class DecideToolInput(BaseModel):
    query: str = Field(description="User query in natural language")
    metadata: str = Field(description="Database schema or metadata description")

@tool("decide_tool", args_schema=DecideToolInput, return_direct=True)
def decide_tool(query: str, metadata: str) -> str:
    """
    NLU Router: Analyzes user query to decide the next action:
    1. 'execute_sql_query': Internal database data.
    2. 'web_search': External knowledge.
    3. 'reset_memory': User wants to clear context/forget history.
    """
    
    if not GROQ_API_KEY:
        logger.critical("GROQ_API_KEY missing. Defaulting to SQL.")
        return "execute_sql_query"

    try:
        client = Groq(api_key=GROQ_API_KEY)

        # Updated Prompt with Reset Logic
        base_system_prompt = (
            "You are an intelligent query router. Select the correct tool based on the user's intent.\n\n"
            "TOOLS:\n"
            "1. 'execute_sql_query': User asks about data in [METADATA] (aggregations, lists, metrics).\n"
            "2. 'web_search': User asks for external facts, news, or general concepts.\n"
            "3. 'reset_memory': User explicitly asks to 'forget', 'reset', 'clear history', or 'start fresh'.\n\n"
            "RULES:\n"
            "- 'reset_memory' has HIGHEST priority if keywords like 'clear', 'wipe', 'forget' appear.\n"
            "- Return ONLY the exact tool string."
        )

        try:
            prompt_path = Path("system_prompt.txt")
            if prompt_path.exists():
                system_instruction = prompt_path.read_text(encoding="utf-8")
            else:
                system_instruction = base_system_prompt
        except Exception:
            system_instruction = base_system_prompt

        messages = [
            {
                "role": "system",
                "content": system_instruction
            },
            {
                "role": "user",
                "content": f"[METADATA_START]\n{metadata}\n[METADATA_END]\n\nUser Query: \"{query}\""
            }
        ]

        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=messages,
            temperature=0.0,
            max_tokens=15,
            stop=["\n", " "]
        )

        decision = response.choices[0].message.content.strip().lower()
        logger.info(f"Groq NLU Routing Decision: {decision} | Query: {query}")

        if "reset" in decision or "memory" in decision or "clear" in decision:
            return "reset_memory"
        elif "sql" in decision or "database" in decision:
            return "execute_sql_query"
        elif "web" in decision or "search" in decision:
            return "web_search"
        else:
            return "execute_sql_query" # Safe fallback

    except Exception as e:
        logger.error(f"NLU Tool Failure: {str(e)}")
        return "execute_sql_query"