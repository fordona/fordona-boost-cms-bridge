from fastapi import APIRouter

from boost_bridge.api.routes import lessons, modules, questions

api_router = APIRouter(prefix="/v1")
api_router.include_router(modules.router)
api_router.include_router(lessons.router)
api_router.include_router(questions.router)
