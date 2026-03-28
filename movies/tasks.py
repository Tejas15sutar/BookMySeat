import time
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

def send_ticket_email(booking_data):
    retries = 3

    for attempt in range(retries):
        try:
            print("📧 Preparing email...")  # 👈 ADD

            subject = "Your Movie Ticket Confirmation"
            to_email = booking_data['email']

            html_content = render_to_string(
                'emails/ticket_confirmation.html',
                booking_data
            )

            email = EmailMultiAlternatives(
                subject,
                "Booking Confirmation",
                settings.EMAIL_HOST_USER,
                [to_email]
            )

            email.attach_alternative(html_content, "text/html")
            email.send()

            print("✅ Email sent successfully")
            return

        except Exception as e:
            print(f"❌ Attempt {attempt+1} failed: {e}")
            time.sleep(2)

    print("❌ All retry attempts failed")