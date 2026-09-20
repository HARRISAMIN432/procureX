from celery import Celery  # type: ignore[import-untyped]

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "procurex",
    broker=settings.rabbitmq_url.get_secret_value(),
    backend=settings.redis_url.get_secret_value(),
    include=["app.workers.documents", "app.workers.evaluations"],
)
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "procurex.document_scan": {"queue": "documents.security"},
        "procurex.evaluation_analysis": {"queue": "ai.evaluations"},
    },
)
