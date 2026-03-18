import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import get_settings

settings = get_settings()


def send_email(
    to_email: str,
    subject: str,
    body: str,
    is_html: bool = True,
):
    """
    Send email via AWS SES SMTP
    """

    msg = MIMEMultipart()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = settings.EMAIL_FROM
    msg["X-Mailer"] = "MaoniMarket"

    mime_type = "html" if is_html else "plain"
    msg.attach(MIMEText(body, mime_type))

    try:
        with smtplib.SMTP(settings.SES_SMTP_HOST, settings.SES_SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SES_SMTP_USER, settings.SES_SMTP_PASS)
            server.send_message(msg)

    except Exception as e:
        # Keep it simple for now — later we log to DB
        print(f"[EMAIL ERROR] {str(e)}")
        raise
