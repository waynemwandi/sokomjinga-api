# app/services/email_templates/deposit_success.py
from app.services.email_templates.base import render_email_layout


def render_deposit_success_email(user, amount_cents: int) -> str:
    amount_kes = amount_cents / 100

    content_html = f"""
    <div style="color:#a3a3a3; margin-bottom:24px;">
        Your deposit has been successfully received.
    </div>

    <div>
        <span style="font-weight:700;">Amount:</span> KES {amount_kes:.2f}
    </div>
    """

    cta_html = """
    <a href="https://maonimarket.com/portfolio"
        style="display:inline-block; background-color:#ffffff; color:#000000; text-decoration:none; font-size:14px; font-weight:700; padding:14px 24px; border-radius:10px;">
        View Portfolio
    </a>
    """

    return render_email_layout(
        title="Deposit Successful",
        content_html=content_html,
        cta_html=cta_html,
    )