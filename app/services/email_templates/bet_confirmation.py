# app/services/email_templates/bet_confirmation.py
from app.services.email_templates.base import render_email_layout


def render_bet_confirmation_email(user, market, outcome, amount_cents: int) -> str:
    amount_kes = amount_cents / 100
    price = outcome.price_cents or 0
    position_color = "#16a34a" if outcome.label.lower() == "yes" else "#b91c1c"

    content_html = f"""
    <div style="color:#a3a3a3; margin-bottom:24px;">
        Your position has been successfully placed.
    </div>

    <div style="font-weight:700; margin-bottom:6px;">Market</div>
    <div style="margin-bottom:24px;">{market.title}</div>

    <div>
        <span style="font-weight:700;">Position:</span>
        <span style="color:{position_color}; font-weight:700;"> {outcome.label.upper()}</span><br/>
        <span style="font-weight:700;">Entry Price:</span> {price}%<br/>
        <span style="font-weight:700;">Amount:</span> KES {amount_kes:.2f}
    </div>
    """

    cta_html = f"""
    <a href="https://maonimarket.com/market/{market.id}"
    style="display:inline-block; background-color:#ffffff; color:#000000; text-decoration:none; font-size:14px; font-weight:700; padding:14px 24px; border-radius:10px;">
        View Market
    </a>
    """

    return render_email_layout(
        title="Bet Confirmed",
        content_html=content_html,
        cta_html=cta_html,
    )