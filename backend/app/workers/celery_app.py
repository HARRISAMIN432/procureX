from celery import Celery  # type: ignore[import-untyped]

from app.core.config import TaskExecutionMode, get_settings

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
    task_always_eager=settings.task_execution_mode is TaskExecutionMode.EAGER,
    task_eager_propagates=False,
    worker_prefetch_multiplier=1,
    task_routes={
        "procurex.document_scan": {"queue": "documents.security"},
        "procurex.document_parse": {"queue": "documents.parsing"},
        "procurex.evaluation_analysis": {"queue": "ai.evaluations"},
    },
)
