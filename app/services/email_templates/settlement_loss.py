# app/services/email_templates/settlement_loss.py
from app.services.email_templates.base import render_email_layout


def render_settlement_loss_email(user, market) -> str:

    content_html = f"""
    <div style="color:#a3a3a3; margin-bottom:24px;">
        This market has been settled.
    </div>

    <div style="font-weight:700; margin-bottom:6px;">Market</div>
    <div style="margin-bottom:24px;">{market.title}</div>

    <div style="color:#737373;">
        Your position did not win this time.
    </div>
    """

    cta_html = """
    <a href="https://maonimarket.com/portfolio"
        style="display:inline-block; background-color:#ffffff; color:#000000; text-decoration:none; font-size:14px; font-weight:700; padding:14px 24px; border-radius:10px;">
        View Portfolio
    </a>
    """

    return render_email_layout(
        title="Market Settled",
        content_html=content_html,
        cta_html=cta_html,
    )