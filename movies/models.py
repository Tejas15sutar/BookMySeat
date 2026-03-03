from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import urllib.parse
from django.utils import timezone



def validate_youtube_url(value):
    parsed = urllib.parse.urlparse(value)

    
    if "youtu.be" in parsed.netloc:
        video_id = parsed.path.strip("/")
        if len(video_id) != 11:
            raise ValidationError("Enter a valid YouTube URL.")

    
    elif "youtube.com" in parsed.netloc:
        query = urllib.parse.parse_qs(parsed.query)
        if "v" not in query or len(query["v"][0]) != 11:
            raise ValidationError("Enter a valid YouTube URL.")

    else:
        raise ValidationError("Enter a valid YouTube URL.")


class Movie(models.Model):
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to="movies/")
    rating = models.DecimalField(max_digits=3, decimal_places=1)
    cast = models.TextField()
    description = models.TextField(blank=True, null=True)

    trailer_url = models.URLField(
        blank=True,
        null=True,
        validators=[validate_youtube_url]
    )

    def get_youtube_id(self):
        if not self.trailer_url:
            return None

        parsed = urllib.parse.urlparse(self.trailer_url)

        # Short youtu.be URL
        if "youtu.be" in parsed.netloc:
            return parsed.path.strip("/")

        # Full youtube.com URL
        if "youtube.com" in parsed.netloc:
            query = urllib.parse.parse_qs(parsed.query)
            if "v" in query:
                return query["v"][0]

        return None

    def __str__(self):
        return self.name


class Theater(models.Model):
    name = models.CharField(max_length=255)
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name="theaters"
    )
    time = models.DateTimeField()

    def __str__(self):
        return f'{self.name} - {self.movie.name} at {self.time}'


class Seat(models.Model):
    theater = models.ForeignKey(
        Theater,
        on_delete=models.CASCADE,
        related_name="seats"
    )
    seat_number = models.CharField(max_length=10)

    is_booked = models.BooleanField(default=False)
    reserved_until = models.DateTimeField(null=True, blank=True)

    def is_available(self):
        if self.is_booked:
            return False
        if self.reserved_until and self.reserved_until > timezone.now():
            return False
        return True

    def __str__(self):
        return f'{self.seat_number} in {self.theater.name}'

class Booking(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_bookings"
    )
    seat = models.OneToOneField(Seat, on_delete=models.CASCADE)
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name="movie_bookings"
    )
    theater = models.ForeignKey(
        Theater,
        on_delete=models.CASCADE,
        related_name="theater_bookings"
    )
    booked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Booking by {self.user.username} for {self.seat.seat_number} at {self.theater.name}'