# app/services/email_templates/settlement_win.py
from app.services.email_templates.base import render_email_layout


def render_settlement_win_email(user, market, payout_cents: int) -> str:
    payout_kes = payout_cents / 100

    content_html = f"""
    <div style="color:#16a34a; margin-bottom:24px; font-weight:700;">
        You won this market.
    </div>

    <div style="font-weight:700; margin-bottom:6px;">Market</div>
    <div style="margin-bottom:24px;">{market.title}</div>

    <div>
        <span style="font-weight:700;">Payout:</span>
        <span style="color:#16a34a; font-weight:700;"> KES {payout_kes:.2f}</span>
    </div>
    """

    cta_html = """
    <a href="https://maonimarket.com/portfolio"
        style="display:inline-block; background-color:#ffffff; color:#000000; text-decoration:none; font-size:14px; font-weight:700; padding:14px 24px; border-radius:10px;">
        View Portfolio
    </a>
    """

    return render_email_layout(
        title="Market Settled — You Won",
        content_html=content_html,
        cta_html=cta_html,
    )