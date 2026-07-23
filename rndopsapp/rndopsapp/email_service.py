import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import frappe

from rndopsapp.rndopsapp.email_config import EMAIL_APP_PASSWORD

_EMAIL_FROM = "rndapp@rnd.iitg.ac.in"
_EMAIL_APP_PASSWORD = EMAIL_APP_PASSWORD
_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587
_RECIPIENTS = ["ernd@iitg.ac.in", "proman@iitg.ac.in", "mky@iisi.iitg.ac.in"]


def send_email(
    subject: str,
    message: str,
    html: bool = False,
    attachments: list[tuple[str, bytes, str]] | None = None,
):
    """
    Send an internal email from rndapp@rnd.iitg.ac.in to the fixed recipients.

    Args:
        subject     : email subject
        message     : email body (plain text or HTML)
        html        : if True, sends message as text/html; otherwise text/plain
        attachments : list of (filename, bytes, content_type) tuples
    """
    if not message:
        frappe.throw("message cannot be blank.")

    msg = MIMEMultipart("mixed")
    msg["From"] = _EMAIL_FROM
    msg["To"] = ", ".join(_RECIPIENTS)
    msg["Subject"] = subject

    mime_type = "html" if html else "plain"
    msg.attach(MIMEText(message, mime_type))

    for filename, data, content_type in (attachments or []):
        main_type, sub_type = (
            content_type.split("/", 1) if "/" in content_type else ("application", "octet-stream")
        )
        part = MIMEBase(main_type, sub_type)
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(_EMAIL_FROM, _EMAIL_APP_PASSWORD)
            server.sendmail(_EMAIL_FROM, _RECIPIENTS, msg.as_string())

        return {"status": "sent"}

    except smtplib.SMTPAuthenticationError:
        frappe.log_error("SMTP authentication failed — check app password.", "email_service")
        return {"status": "error", "error": "Authentication failed"}

    except smtplib.SMTPException as exc:
        frappe.log_error(frappe.get_traceback(), "email_service")
        return {"status": "error", "error": str(exc)}

    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), "email_service")
        return {"status": "error", "error": str(exc)}
