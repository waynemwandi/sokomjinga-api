from app.services.email import send_email


def send_bet_confirmation(user, market, outcome, amount_cents: int):
    """
    Send bet confirmation email
    """

    subject = f"Bet Confirmed — {market.title}"

    amount_kes = amount_cents / 100

    body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #0b0f19; color: #ffffff; padding: 20px;">
            <div style="max-width: 600px; margin: auto; background-color: #121826; padding: 20px; border-radius: 10px;">
                
                <h2 style="color: #00d4ff;">MaoniMarket</h2>

                <p>Your bet has been successfully placed.</p>

                <hr style="border: 0; border-top: 1px solid #2a2f3a;" />

                <p><strong>Market:</strong> {market.title}</p>
                <p><strong>Position:</strong> {outcome.label.upper()}</p>
                <p><strong>Amount:</strong> KES {amount_kes:.2f}</p>

                <hr style="border: 0; border-top: 1px solid #2a2f3a;" />

                <p style="font-size: 12px; color: #9ca3af;">
                    You are receiving this email because you placed a bet on MaoniMarket.
                </p>

            </div>
        </body>
    </html>
    """

    send_email(
        to_email=user.email,
        subject=subject,
        body=body,
    )
