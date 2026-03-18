import logging

from app.services.email import send_email

logger = logging.getLogger("maoni.email.test")


if __name__ == "__main__":
    send_email(
        to_email="mwandiwayne@gmail.com",
        cc=[
            "muthusifred.fm@gmail.com",
            "kyalokyengo@gmail.com",
        ],
        subject="MaoniMarket | Email System Live",
        body="""
        <html>
            <body>
                <h2>MaoniMarket</h2>
                <p>Email delivery is now live in production.</p>

                <p><b>Status:</b> Operational</p>
                <p>This is a system-generated transactional email.</p>

                <br/>
                <p>— MaoniMarket System</p>
            </body>
        </html>
        """,
    )

    print("Email sent")
    logger.info("Test email sent successfully")
