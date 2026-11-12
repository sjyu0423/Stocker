from marketmind.worker.celery_app import celery_app


@celery_app.task(name="marketmind.worker.healthcheck")  # type: ignore[untyped-decorator]
def healthcheck() -> dict[str, str]:
    """Infrastructure smoke task; collection schedules arrive in a later milestone."""
    return {"status": "ok"}
