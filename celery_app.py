import os
from celery import Celery

app = Celery(
    "llm_auth_agent",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
)
app.conf.task_routes = {"tasks.*": {"queue": "auth"}}
app.conf.imports = ("tasks_signup_minimal",)