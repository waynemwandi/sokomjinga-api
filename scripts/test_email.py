from app.services.email import send_email

if __name__ == "__main__":
    send_email(
        to_email="mwandiwayne@gmail.com",
        subject="SES Test - MaoniMarket",
        body="""
        <html>
            <body>
                <h2>MaoniMarket</h2>
                <p>Email delivery is working.</p>
            </body>
        </html>
        """,
    )

    print("Email sent")
