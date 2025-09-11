# llm_chains.py
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain
from langchain.prompts import ChatPromptTemplate
from typing import Optional
import config
from memory_store import get_or_create_memory

# initialize llm (same config as original)
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=config.GEMINI_API_KEY,
    temperature=0
)

# template for SQL generation (keeps original wording)
sql_prompt = ChatPromptTemplate.from_template("""
You are an expert SQL generator for Microsoft SQL Server.

Database Schema:
{schema}

Conversation so far:
{history}

Task:
- Generate ONLY a valid T-SQL query (no explanations, no markdown).
- Use table/column names exactly as in schema.
- If user request is not SQL-related, return exactly:
  "⚠️ This doesn’t look like a database query. Please try asking something related to SQL or databases."

User Request: {user_input}
""")

def generate_sql_query(prompt: str, session_id: Optional[str] = None) -> str:
    try:
        sid = session_id or "default"
        memory = get_or_create_memory(sid)

        sql_chain = LLMChain(
            llm=llm,
            prompt=sql_prompt,
            memory=memory,
            verbose=False
        )

        response = sql_chain.run(schema="", user_input=prompt)  # schema will be provided by API layer
        sql = (
            response.strip()
            .replace("```sql", "")
            .replace("```", "")
            .strip(";")
            .strip()
        )
        return sql if sql else "⚠️ This doesn’t look like a database query."
    except Exception as e:
        return f"Error from Gemini (LangChain): {str(e)}"


def generate_suggestions(error_message: str, user_input: str) -> str:
    try:
        suggestion_prompt = ChatPromptTemplate.from_template("""
        A user tried this SQL input: "{user_input}"
        The database returned this error: "{error}"

        Task:
        - Generate 2 to 3 clear and actionable tips to fix the query.
        - Format them as: "Tip 1: ...", "Tip 2: ...", etc.
        - Do NOT return SQL code; only give helpful guidance.
        - Separate each suggestion with ^.
        """)

        suggestion_chain = LLMChain(llm=llm, prompt=suggestion_prompt, verbose=False)
        return suggestion_chain.run(user_input=user_input, error=error_message)
    except Exception:
        return (
            "Tip 1: Check table and column names.^"
            "Tip 2: Review SQL syntax.^"
            "Tip 3: Ensure correct query structure."
        )
