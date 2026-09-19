from fastapi import APIRouter

from app.api.v1.routes import organizations

api_router = APIRouter()
api_router.include_router(organizations.router)
