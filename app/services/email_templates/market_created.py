# app/services/email_templates/market_created.py
from app.services.email_templates.base import render_email_layout


def render_market_created_email(market) -> str:

    content_html = f"""
    <div style="color:#a3a3a3; margin-bottom:24px;">
        A new market is now live.
    </div>

    <div style="font-weight:700; margin-bottom:6px;">Market</div>
    <div style="margin-bottom:24px;">{market.title}</div>
    """

    cta_html = f"""
    <a href="https://maonimarket.com/market/{market.id}"
    style="display:inline-block; background-color:#ffffff; color:#000000; text-decoration:none; font-size:14px; font-weight:700; padding:14px 24px; border-radius:10px;">
        View Market
    </a>
    """

    return render_email_layout(
        title="New Market Live",
        content_html=content_html,
        cta_html=cta_html,
    )