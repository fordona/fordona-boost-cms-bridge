from fastapi import APIRouter

from boost_bridge.api.routes import lessons

api_router = APIRouter(prefix="/v1")
api_router.include_router(lessons.router)
