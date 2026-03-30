from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import urllib.parse
from django.utils import timezone
import uuid


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
    
    
class EmailOTP(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

class Payment(models.Model):
    razorpay_order_id = models.CharField(max_length=200)
    razorpay_payment_id = models.CharField(max_length=200, null=True, blank=True)
    razorpay_signature = models.TextField(null=True, blank=True)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True)
    status = models.CharField(
        max_length=20,
        choices=[("PENDING", "pending"), ("SUCCESS", "Success"), ("FAILED", "Failed")],
        default="PENDING"
    )
    created_at = models.DateTimeField(auto_now_add=True)

class Genre(models.Model):
    name = models.CharField(max_length= 100, unique = True, db_index = True)
    
    def __str__(self):
        return self.name

class Language(models.Model):
    name = models.CharField(max_length= 100, unique = True, db_index = True)
    
    def __str__(self):
        return self.name
    
class Movie(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    genre = models.ManyToManyField(Genre, related_name= "movies")
    language = models.ForeignKey(Language, on_delete=models.CASCADE, null=True,blank=True)
    image = models.ImageField(upload_to="movies/")
    rating = models.DecimalField(max_digits=3, decimal_places=1, db_index=True)
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
    rows = models.IntegerField(default=10)
    seats_per_row = models.IntegerField(default=12)
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

    locked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    
    def is_available(self):
        if self.is_booked:
            return False
        if self.reserved_until and self.reserved_until > timezone.now():
            return False
        return True

    def __str__(self):
        return f'{self.seat_number} in {self.theater.name}'

class Booking(models.Model):
    
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('CANCELLED', 'Cancelled'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_bookings"
    )

    seat = models.ForeignKey(
        Seat,
        on_delete=models.CASCADE
    )

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

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        db_index=True
    )

    booked_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    payment = models.ForeignKey(
        "Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings"
    )

    def __str__(self):
        return f'Booking by {self.user.username} for {self.seat.seat_number} at {self.theater.name}'