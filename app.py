import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api_endpoints.fastapiEndpoints import router
from utilities.utils import get_settings

app = FastAPI(title="SQL Assistant API")

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(app, host=settings.get("SERVER_IP"), port=settings.get("SERVER_PORT"))