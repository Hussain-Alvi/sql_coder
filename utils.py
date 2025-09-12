# utils.py
import subprocess

def normalize_input(user_input: str) -> str:
    return user_input.strip()


def looks_like_sql(text: str) -> bool:
    sql_keywords = ("select", "insert", "update", "delete", "create", "alter", "drop", "with", "exec", "use", "set")
    cleaned = text.strip().lower()
    tokens = cleaned.split()
    for token in tokens:
        if token in sql_keywords:
            return True
    return False


############################