from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict

from utilities.utils import get_settings, get_logger, get_db_connection
from data_validations.data_models import MessagesList
from api_endpoints.endpoints import router


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

settings = get_settings()
logger = get_logger(settings)
db_conn_str = get_db_connection(settings, logger)

# ✅ Shared chat history state – accessed across endpoints
messages_history: Dict[str, MessagesList] = {}

# ✅ Attach shared objects to app for access in router
app.state.settings = settings
app.state.logger = logger
app.state.db_conn_str = db_conn_str
app.state.messages_history = messages_history

# ✅ Include Router
app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host=settings.get("SERVER_IP"), port=settings.get("SERVER_PORT"))