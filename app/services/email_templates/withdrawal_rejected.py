from app.services.email_templates.base import render_email_layout


def render_withdrawal_rejected_email(user, withdrawal) -> str:
    amount_kes = withdrawal.amount_cents / 100
    reason = withdrawal.reason or "Please contact support for more information."

    content_html = f"""
    <div style="color:#a3a3a3; margin-bottom:24px;">
        Your withdrawal request was not processed. The funds have been returned to your wallet.
    </div>

    <div>
        <span style="font-weight:700;">Amount:</span> KES {amount_kes:.2f}<br/>
        <span style="font-weight:700;">Reason:</span> {reason}
    </div>
    """

    cta_html = """
    <a href="https://maonimarket.com/portfolio"
        style="display:inline-block; background-color:#ffffff; color:#000000; text-decoration:none; font-size:14px; font-weight:700; padding:14px 24px; border-radius:10px;">
        View Portfolio
    </a>
    """

    return render_email_layout(
        title="Withdrawal Not Processed",
        content_html=content_html,
        cta_html=cta_html,
    )
