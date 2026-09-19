from fastapi import APIRouter

from app.api.v1.routes import (
    approvals,
    documents,
    extractions,
    organizations,
    requisitions,
    sourcing,
    suppliers,
)

api_router = APIRouter()
api_router.include_router(organizations.router)
api_router.include_router(requisitions.router)
api_router.include_router(approvals.router)
api_router.include_router(suppliers.router)
api_router.include_router(sourcing.router)
api_router.include_router(documents.router)
api_router.include_router(extractions.router)
