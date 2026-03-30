from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from django.template.loader import render_to_string
from django.conf import settings
import logging
import threading 

logger = logging.getLogger(__name__)

def send_ticket_email(booking_data):
    try:
        html_content = render_to_string(
            "emails/ticket_confirmation.html",
            booking_data
        )

        message = Mail(
            from_email='no-reply@bookmyseat.com',  
            to_emails=booking_data["email"],
            subject='🎟 Your Movie Ticket Confirmation',
            html_content=html_content
        )

        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)

        logger.info(f"Email sent successfully: {response.status_code}")

    except Exception as e:
        logger.error(f"Email failed: {str(e)}")
    
def send_email_async(booking_data):
    thread = threading.Thread(
        target=send_ticket_email,
        args=(booking_data,)
    )
    thread.start()