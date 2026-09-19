from fastapi import APIRouter

from app.api.v1.routes import approvals, organizations, requisitions, suppliers

api_router = APIRouter()
api_router.include_router(organizations.router)
api_router.include_router(requisitions.router)
api_router.include_router(approvals.router)
api_router.include_router(suppliers.router)
