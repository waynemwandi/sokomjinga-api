# app/services/email.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from app.core.config import get_settings
from app.db.models import EmailLog
from app.db.session import SessionLocal

settings = get_settings()


def send_email(
    to_email: str,
    subject: str,
    body: str,
    is_html: bool = True,
    cc: Optional[List[str]] = None,
):
    """
    Send email via AWS SES SMTP + log to DB
    """

    db = SessionLocal()

    log = EmailLog(
        to_email=to_email,
        subject=subject,
        status="pending",
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    msg = MIMEMultipart()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = settings.EMAIL_FROM
    msg["X-Mailer"] = "MaoniMarket"
    recipients = [to_email]
    if cc:
        msg["Cc"] = ", ".join(cc)
        recipients.extend(cc)

    mime_type = "html" if is_html else "plain"
    msg.attach(MIMEText(body, mime_type))

    try:
        with smtplib.SMTP(settings.SES_SMTP_HOST, settings.SES_SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SES_SMTP_USER, settings.SES_SMTP_PASS)
            server.sendmail(
                settings.EMAIL_FROM,
                recipients,
                msg.as_string(),
            )

        # Success
        log.status = "sent"
        db.commit()

    except Exception as e:
        log.status = "failed"
        log.error_message = str(e)
        db.commit()
        raise

    finally:
        db.close()
