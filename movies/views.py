from django.shortcuts import render , redirect , get_object_or_404
from .models import Movie,Theater,Seat,Booking, Payment ,Language
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from django.conf import settings
import razorpay
import json
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Sum, Count
from django.db.models.functions import ExtractHour
from django.core.cache import cache
from django.core.paginator import Paginator

def admin_check(user):
    return user.is_staff


@csrf_exempt
def payment_webhook(request):
    payload = request.body
    signature = request.headers.get("x-razorpay-signature")

    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )

    try:
        client.utility.verify_webhook_signature(
            payload,
            signature,
            settings.RAZORPAY_WEBHOOK_SECRET
        )
    except Exception:
        return HttpResponse(status=400)

    data = json.loads(payload)

    order_id = data["payload"]["payment"]["entity"]["order_id"]
    payment_id = data["payload"]["payment"]["entity"]["id"]

    try:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(
                razorpay_order_id=order_id
            )

            if payment.status == "SUCCESS":
                return HttpResponse(status=200)

            payment.razorpay_payment_id = payment_id
            payment.status = "SUCCESS"
            payment.save()

            booking = payment.booking
            booking.status = "CONFIRMED"
            booking.save()
            
            seat = booking.seat
            if seat.reserved_until and seat.reserved_until < timezone.now():
                return HttpResponse(status=400)
            
            seat.is_booked = True
            seat.reserved_until = None
            seat.save()

    except Payment.DoesNotExist:
        return HttpResponse(status=404)

    return HttpResponse(status=200)


@transaction.atomic
def reserve_seat(request, seat_id):
    try:
        seat = Seat.objects.select_for_update().get(id=seat_id)

        if seat.is_booked:
            return JsonResponse({"error": "Seat already booked"}, status=400)

        if seat.reserved_until and seat.reserved_until > timezone.now():
            return JsonResponse({"error": "Seat already reserved"}, status=400)

        seat.reserved_until = timezone.now() + timedelta(minutes=2)
        seat.save()

        return JsonResponse({"message": "Seat reserved for 2 minutes"})

    except Seat.DoesNotExist:
        return JsonResponse({"error": "Seat not found"}, status=404)


@transaction.atomic
def confirm_booking(request, seat_id):
    try:
        seat = Seat.objects.select_for_update().get(id=seat_id)

        if seat.reserved_until and seat.reserved_until > timezone.now():
            seat.is_booked = True
            seat.reserved_until = None
            seat.save()
            return JsonResponse({"message": "Seat booked successfully"})

        return JsonResponse({"error": "Reservation expired"}, status=400)

    except Seat.DoesNotExist:
        return JsonResponse({"error": "Seat not found"}, status=404)


from django.shortcuts import render
from django.core.paginator import Paginator
from django.db.models import Count
from .models import Movie, Language


def movie_list(request):
    search_query = request.GET.get('search')
    genres = request.GET.getlist('genre')
    languages = request.GET.getlist('language')
    sort = request.GET.get('sort', 'name')

    movies = Movie.objects.all()

    
    if search_query:
        movies = movies.filter(name__icontains=search_query)

    
    if genres:
        movies = movies.filter(genre__name__in=genres)

    
    if languages:
        movies = movies.filter(language__name__in=languages)

    
    movies = movies.distinct()

    
    genre_counts = movies.exclude(genre__name__isnull=True).values(
    'genre__name'
).annotate(
    count=Count('id')
)

    
    allowed_sort = ['name', 'release_date', '-release_date', 'rating', '-rating']
    if sort in allowed_sort:
        movies = movies.order_by(sort)

    
    movies = movies.select_related('language').prefetch_related('genre')

    
    paginator = Paginator(movies, 8)
    page = request.GET.get('page')
    movies = paginator.get_page(page)

    return render(request, 'movies/movie_list.html', {
        'movies': movies,
        'genre_counts': genre_counts,
        'languages': Language.objects.all()
    })

def movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    return render(request, 'movies/movie_detail.html', {'movie': movie})


def theater_list(request,movie_id):
    movie = get_object_or_404(Movie,id = movie_id)
    theater = Theater.objects.filter(movie=movie)

    return render(request, 'movies/theater_list.html',{
        'movie':movie,
        'theaters':theater
    })


@login_required(login_url='/login/')
def book_seats(request, theater_id):

    theaters = get_object_or_404(Theater, id=theater_id)

    Seat.objects.filter(
        reserved_until__lt=timezone.now(),
        is_booked=False
    ).update(reserved_until=None)

    seats = Seat.objects.filter(theater=theaters)

    if request.method == 'POST':

        selected_seats = request.POST.getlist('seats')
        error_seats = []

        if not selected_seats:
            return render(request, "movies/seat_selection.html", {
                'theater': theaters,
                'seats': seats,
                'error': "No seat selected"
            })

        with transaction.atomic():

            created_bookings = []

            for seat_id in selected_seats:

                try:
                    seat = Seat.objects.select_for_update().get(
                        id=seat_id,
                        theater=theaters
                    )
                except Seat.DoesNotExist:
                    continue

                if seat.is_booked:
                    error_seats.append(seat.seat_number)
                    continue

                if seat.reserved_until and seat.reserved_until > timezone.now():
                    error_seats.append(seat.seat_number)
                    continue

                seat.reserved_until = timezone.now() + timedelta(minutes=2)
                seat.save()

                booking = Booking.objects.create(
                    user=request.user,
                    seat=seat,
                    movie=theaters.movie,
                    theater=theaters,
                    status="PENDING"
                )

                created_bookings.append(booking)

        if error_seats:
            error_message = f"The following seats are not available: {', '.join(error_seats)}"
            return render(request, 'movies/seat_selection.html', {
                'theater': theaters,
                'seats': seats,
                'error': error_message
            })

        if created_bookings:
            return redirect('create_payment', booking_id=created_bookings[0].id)

    return render(request, 'movies/seat_selection.html', {
        'theater': theaters,
        'seats': seats
    })


def create_payment(request, booking_id):
    
    booking = get_object_or_404(Booking, id=booking_id)

    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )

    amount = 200  # ₹200

    # Check if payment already exists
    payment = Payment.objects.filter(booking=booking).first()

    if payment:
        order_id = payment.razorpay_order_id
    else:
        order = client.order.create({
            "amount": amount,
            "currency": "INR",
            "payment_capture": 1
        })

        payment = Payment.objects.create(
            booking=booking,
            razorpay_order_id=order["id"]
        )

        order_id = order["id"]

    return render(request, "movies/payment_page.html", {
        "booking": booking,
        "order_id": order_id,
        "razorpay_key": settings.RAZORPAY_KEY_ID,
        "amount": amount
    })
    
    
@login_required
@user_passes_test(admin_check)
def admin_dashboard(request):

    data = cache.get("admin_dashboard_data")

    if not data:

        today = timezone.now().date()

        # Daily revenue
        daily_revenue = Booking.objects.filter(
            booked_at__date=today,
            status="CONFIRMED"
        ).aggregate(total=Sum("amount"))["total"] or 0

        # Weekly revenue
        weekly_revenue = Booking.objects.filter(
            booked_at__gte=today - timedelta(days=7),
            status="CONFIRMED"
        ).aggregate(total=Sum("amount"))["total"] or 0

        # Monthly revenue
        monthly_revenue = Booking.objects.filter(
            booked_at__month=today.month,
            status="CONFIRMED"
        ).aggregate(total=Sum("amount"))["total"] or 0

        # Most popular movies
        popular_movies = Booking.objects.values(
            "movie__name"
        ).annotate(
            total_bookings=Count("id")
        ).order_by("-total_bookings")[:5]

        # Busiest theaters
        busiest_theaters = Booking.objects.values(
            "theater__name"
        ).annotate(
            total_bookings=Count("id")
        ).order_by("-total_bookings")[:5]

        # Peak booking hours
        peak_hours = Booking.objects.annotate(
            hour=ExtractHour("booked_at")
        ).values("hour").annotate(
            total=Count("id")
        ).order_by("-total")[:5]

        # Cancellation rate
        total_bookings = Booking.objects.count()

        cancelled_bookings = Booking.objects.filter(
            status="CANCELLED"
        ).count()

        cancellation_rate = 0

        if total_bookings > 0:
            cancellation_rate = (cancelled_bookings / total_bookings) * 100

        data = {
            "daily_revenue": daily_revenue,
            "weekly_revenue": weekly_revenue,
            "monthly_revenue": monthly_revenue,
            "popular_movies": popular_movies,
            "busiest_theaters": busiest_theaters,
            "peak_hours": peak_hours,
            "cancellation_rate": cancellation_rate,
        }

        # Cache for 5 minutes
        cache.set("admin_dashboard_data", data, 300)

    return render(request, "admin/dashboard.html", data)