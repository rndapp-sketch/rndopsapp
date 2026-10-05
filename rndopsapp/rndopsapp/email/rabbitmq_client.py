"""Publishes an Email Manager notification job as a real Celery task."""


def publish_task(log_name: str, to_addresses: list[str], subject: str, html_body: str) -> str:
    """Enqueues pragati.send_status_email via Celery. Returns the task_id for Email Send Logs."""
    from rndopsapp.rndopsapp.email.celery_app import send_status_email

    result = send_status_email.apply_async(
        kwargs={
            "log_name": log_name,
            "to_addresses": to_addresses,
            "subject": subject,
            "html_body": html_body,
        }
    )
    return result.id
