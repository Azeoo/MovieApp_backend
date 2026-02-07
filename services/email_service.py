import smtplib
from email.mime.text import MIMEText
from logger import LoggerFactory
from flask import current_app

logger = LoggerFactory.get_logger(__name__)

def send_otp_email(receiver_email:str, otp:str):
    logger.info(f"Sending OTP through E-mail")
    
    SENDER_EMAIL = current_app.config["SENDER_EMAIL"]
    APP_PASSWORD = current_app.config["APP_PASSWORD"]

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, Helvetica, sans-serif; background-color: #f5f5f5; padding: 20px;">

        <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
            <td align="center">
            <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; padding: 24px; border-radius: 6px;">

                <tr>
                <td>
                    <p>Hello,</p>

                    <p>
                    Thank you for signing up for our
                    <strong>Premium Membership</strong>.
                    </p>

                    <p>
                    To complete your email verification, please use the
                    One-Time Password (OTP) below:
                    </p>

                    <p style="font-size: 18px; font-weight: bold; margin: 20px 0;">
                    Your OTP: <span style="letter-spacing: 2px;">{otp}</span>
                    </p>

                    <p>
                    Please do not share this code with anyone for security reasons.
                    </p>

                    <p>
                    If you did not request this verification, you can safely ignore this email.
                    </p>

                    <p>
                    Thank you for choosing us!
                    </p>

                </td>
                </tr>

            </table>
            </td>
        </tr>
        </table>

    </body>
    </html>
    """

    msg = MIMEText(html, "html")
    msg["Subject"] = "Verify Your Email with OTP – Premium Membership"
    msg["From"] = SENDER_EMAIL
    msg["To"] = receiver_email

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email sent Successfully")
        return True
    except Exception as e:
        logger.exception(f"Exception occured while sending  OTP E-mail")
        return False

