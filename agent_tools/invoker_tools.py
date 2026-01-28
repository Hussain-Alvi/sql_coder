import logging
from langchain_core.tools import tool
from dynaconf import Dynaconf

# Internal imports
from agents.db_agent import sql_agent
from agent_tools.websearch import web_search_tool
from agent_tools.memory import thread_memory_manager
from data_models.data_models import MessagesList

logger = logging.getLogger(__name__)

def get_router_tools(
    settings: Dynaconf,
    db_conn_str: str,
    conversation: MessagesList,
    thread_id: str
):
    """
    Factory function to create and return tools with necessary context injected.
    """

    @tool("ask_database")
    def call_sql_agent(query: str) -> str:
        """
        Use this tool for questions about internal data, users, metrics,
        tables, or any data stored in the database.
        Input should be the specific question for the database.
        """
        logger.info(f"🔄 Routing to SQL Agent: {query}")

        return sql_agent(
            settings=settings,
            logger=logger,
            db_conn_str=db_conn_str,
            conversation=conversation
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

    return [call_sql_agent, call_web_search, call_memory_reset]