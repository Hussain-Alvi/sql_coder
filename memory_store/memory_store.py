# memory_store.py
from typing import Dict, List

class ThreadMemoryStore:
    """
    Thread-scoped short-term memory store.
    Memory lives only for the duration of a session (thread).
    """

    def __init__(self):
        self._store: Dict[str, List[str]] = {}

    def get(self, thread_id: str) -> List[str]:
        return self._store.get(thread_id, [])

    def append(self, thread_id: str, value: str):
        if thread_id not in self._store:
            self._store[thread_id] = []
        self._store[thread_id].append(value)

    def reset(self, thread_id: str):
        self._store[thread_id] = []
