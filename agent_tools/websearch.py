import logging
from typing import Dict, Any, Optional
from langchain.tools import tool
from pydantic import BaseModel, Field
from groq import Groq

logger = logging.getLogger("tools")

class WebSearchInput(BaseModel):
    query: str = Field(description="Search query for real-time web information")
    max_results: Optional[int] = Field(default=3, description="Max results (1-5)")
        
@tool("web_search", args_schema=WebSearchInput, return_direct=False)
def web_search_tool(query: str) -> Dict[str, Any]:
    """
    Search the web using Groq's compound model for real-time information.
    Returns short, concise answers.
    """
    try:

        from dynaconf import Dynaconf
        settings = Dynaconf(
            settings_files=['settings.toml', '.secrets.toml'],
            environments=True,
            load_dotenv=True,
        )
        
        api_key = settings.get("GROQ_API_KEY")
        if not api_key:
            return {
                "status": "error",
                "message": "GROQ_API_KEY not configured",
                "results": []
            }
        
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="groq/compound",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a helpful agent. ALWAYS give SHORT, CONCISE answers. Maximum 3-4 lines. No tables, no bullet points, just plain short text."
                },
                {
                    "role": "user", 
                    "content": f"Search the web: {query}"
                }
            ],
            max_tokens=200
        )
        
        result_text = response.choices[0].message.content
        
        websites_found = []
        import re
        
        website_pattern = r'\b(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?\b'
        found_sites = re.findall(website_pattern, result_text, re.IGNORECASE)
        
        non_website_words = ['http', 'https', 'com', 'org', 'net', 'www']
        for site in found_sites:
            site_lower = site.lower()
            if ('.' in site_lower and 
                not any(word == site_lower for word in non_website_words) and
                len(site_lower) > 4):
                websites_found.append(site_lower)
        
        websites_found = list(set(websites_found))[:2]
        
        return {
            "status": "success",
            "query": query,
            "source": "groq_compound",
            "results": [{
                "title": f"Web Search" + (f" ({', '.join(websites_found)})" if websites_found else ""),
                "snippet": result_text,
                "url": ""
            }],
            "summary": result_text
        }
        
    except Exception as e:
        logger.error(f"Groq compound search error: {e}")
        return {
            "status": "error",
            "message": f"Web search failed: {str(e)}",
            "results": []
        }
        
logger = logging.getLogger(__name__)