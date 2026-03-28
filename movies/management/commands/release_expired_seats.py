from django.core.management.base import BaseCommand
from django.utils import timezone
from movies.models import Seat


class Command(BaseCommand):
    help = "Release expired seat reservations"

    def handle(self, *args, **kwargs):
        expired_seats = Seat.objects.filter(
            reserved_until__lt=timezone.now(),
            is_booked=False
        )

        count = expired_seats.update(reserved_until=None)

        self.stdout.write(self.style.SUCCESS(f"{count} expired seats released"))