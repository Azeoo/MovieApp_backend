import requests
import os
from logger import LoggerFactory
from flask import current_app

logger = LoggerFactory.get_logger(__name__)

def send_otp_email(sender_email:str, otp:str):
    logger.info(f"Sending OTP through E-mail")
    RESEND_API_KEY = current_app.config["RESEND_API_KEY"]

    RESEND_ENDPOINT = current_app.config["RESEND_ENDPOINT"]


    payload = {
        "from" : "onboarding@resend.dev",
        "to" : [sender_email],
        "subject" : "Verify Your Email with OTP – Premium Membership",
        "html" : f"""
            <p>Hello,</p>

            <p>
                Thank you for signing up for our <strong>Premium Membership</strong>.
            </p>

            <p>
                To complete your email verification, please use the One-Time Password (OTP) below:
            </p>

            <p style="font-size: 18px; font-weight: bold;">
                Your OTP: {otp}
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
        """
    }


    headers = {
        "Authorization" : f"Bearer {RESEND_API_KEY}",
        "Content-Type" : "application/json"
    }

    response = requests.post(url=RESEND_ENDPOINT, json=payload, headers=headers)
    logger.info(f"Raw Response : {response.text}")

    logger.info(f"Email sending status : {response.status_code}")

    return  response.status_code == 200
