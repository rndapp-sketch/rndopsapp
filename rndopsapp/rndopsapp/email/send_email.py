import smtplib
from email.message import EmailMessage

from rndopsapp.rndopsapp.email.email_config import (
    FROM_SENDER as _FROM_SENDER,
    PRORNDADMIN_EMAIL_PASSWORD,
    SMTP_HOST as _SMTP_HOST,
    SMTP_PORT as _SMTP_PORT,
)


def send_email_with_password(to_address: str, subject: str, description: str, html: bool = False) -> bool:
    """
    Send an email from prorndadmin@iitg.ac.in via Microsoft 365 Exchange Online,
    using basic auth over STARTTLS.

    Args:
        to_address  : recipient email address
        subject     : email subject
        description : email body (plain text, or HTML if html=True)
        html        : if True, sends description as text/html; otherwise text/plain

    Returns:
        bool: True if sent successfully, False otherwise
    """
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = _FROM_SENDER
        msg["To"] = to_address

        if html:
            msg.set_content("This email requires an HTML-capable client to view.")
            msg.add_alternative(description, subtype="html")
        else:
            msg.set_content(description)

        server = smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15)
        try:
            server.ehlo()
            server.starttls()
            server.ehlo()

            server.login(_FROM_SENDER, PRORNDADMIN_EMAIL_PASSWORD)
            server.send_message(msg)
        finally:
            server.quit()

        return True

    except Exception:
        import frappe

        frappe.log_error(frappe.get_traceback(), "send_email_with_password failed")
        return False
