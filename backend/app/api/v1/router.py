from fastapi import APIRouter

from app.api.v1.routes import organizations, requisitions

api_router = APIRouter()
api_router.include_router(organizations.router)
api_router.include_router(requisitions.router)
