from app.services.email_templates.base import render_email_layout


def render_withdrawal_completed_email(user, withdrawal) -> str:
    amount_kes = withdrawal.amount_cents / 100
    reference = withdrawal.mpesa_reference or "Manual transfer"

    content_html = f"""
    <div style="color:#a3a3a3; margin-bottom:24px;">
        Your withdrawal has been sent to your saved M-Pesa number.
    </div>

    <div>
        <span style="font-weight:700;">Amount:</span> KES {amount_kes:.2f}<br/>
        <span style="font-weight:700;">Phone:</span> {withdrawal.mpesa_phone or "Saved profile phone"}<br/>
        <span style="font-weight:700;">M-Pesa reference:</span> {reference}
    </div>
    """

    cta_html = """
    <a href="https://maonimarket.com/portfolio"
        style="display:inline-block; background-color:#ffffff; color:#000000; text-decoration:none; font-size:14px; font-weight:700; padding:14px 24px; border-radius:10px;">
        View Portfolio
    </a>
    """

    return render_email_layout(
        title="Withdrawal Sent",
        content_html=content_html,
        cta_html=cta_html,
    )
