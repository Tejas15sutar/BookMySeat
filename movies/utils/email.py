from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from django.template.loader import render_to_string
from django.conf import settings
import logging
import threading 
import os

logger = logging.getLogger(__name__)

def send_ticket_email(booking_data):
    try:
        print("EMAIL FUNCTION STARTED")

        # 
        try:
            html_content = render_to_string(
                "emails/ticket_confirmation.html",
                booking_data
            )
        except Exception as template_error:
            print("TEMPLATE ERROR:", str(template_error))
            html_content = f"""
            <h2>Booking Confirmed</h2>
            <p>Movie: {booking_data.get('movie')}</p>
            <p>Theater: {booking_data.get('theater')}</p>
            <p>Seats: {booking_data.get('seats')}</p>
            <p>Payment ID: {booking_data.get('payment_id')}</p>
            """

        print("📧 Sending to:", booking_data.get("email"))

        message = Mail(
            from_email='no-reply@bookmyseat.com',
            to_emails=booking_data.get("email"),
            subject='🎟 Your Movie Ticket Confirmation',
            html_content=html_content
        )

        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)

        print("✅ SENDGRID STATUS:", response.status_code)

    except Exception as e:
        print("EMAIL ERROR:", str(e))
    
def send_email_async(booking_data):
    thread = threading.Thread(
        target=send_ticket_email,
        args=(booking_data,)
    )
    thread.start()
    

logger = logging.getLogger(__name__)

def send_otp_email(email, otp):
    try:
        message = Mail(
            from_email=settings.DEFAULT_FROM_EMAIL,  
            to_emails=email,
            subject='Your OTP Code',
            html_content=f'<strong>Your OTP is: {otp}</strong>'
        )

        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)

        print("SENDGRID STATUS:", response.status_code)

    except Exception as e:
        print("OTP ERROR:", str(e))