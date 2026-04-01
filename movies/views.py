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
import threading
from .utils.email import send_email_async
from .tasks import send_ticket_email



def admin_check(user):
    return user.is_staff


@csrf_exempt
def payment_webhook(request):
    payload = request.body
    signature = request.headers.get("x-razorpay-signature")
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    try:
        client.utility.verify_webhook_signature(payload, signature, settings.RAZORPAY_WEBHOOK_SECRET)
    except Exception:
        return HttpResponse(status=400)

    data = json.loads(payload)
    order_id = data["payload"]["payment"]["entity"]["order_id"]
    payment_id = data["payload"]["payment"]["entity"]["id"]

    try:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(razorpay_order_id=order_id)

            if payment.status == "SUCCESS":
                return HttpResponse(status=200)

            payment.razorpay_payment_id = payment_id
            payment.status = "SUCCESS"
            payment.save(update_fields=['razorpay_payment_id', 'status'])

            for booking in payment.bookings.all():
                if booking.status != "CONFIRMED":
                    booking.status = "CONFIRMED"
                    booking.save(update_fields=['status'])

                    seat = booking.seat
                    seat.is_booked = True
                    seat.reserved_until = None
                    seat.locked_by = None
                    seat.save(update_fields=['is_booked', 'reserved_until', 'locked_by'])

    except Payment.DoesNotExist:
        return HttpResponse(status=404)

    return HttpResponse(status=200)

@csrf_exempt
def payment_success(request):
    if request.method != "POST":
        return JsonResponse({"status": "invalid request"}, status=400)

    try:
        data = json.loads(request.body)

        payment_id = data.get("razorpay_payment_id")
        order_id = data.get("razorpay_order_id")
        signature = data.get("razorpay_signature")

        if not payment_id or not order_id:
            return JsonResponse({"status": "failed", "message": "Missing data"}, status=400)

        client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )

        # VERIFY SIGNATURE
        client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature
        })

        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(
                razorpay_order_id=order_id
            )

            # prevent double processing
            if payment.status == "SUCCESS":
                return JsonResponse({"status": "already processed"})

            payment.status = "SUCCESS"
            payment.razorpay_payment_id = payment_id
            payment.razorpay_signature = signature
            payment.save()

            bookings = payment.bookings.select_related("seat")

            if not bookings.exists():
                return JsonResponse({"status": "failed", "message": "No bookings found"}, status=400)

            for booking in bookings:
                booking.status = "CONFIRMED"
                booking.save()

                seat = booking.seat
                seat.is_booked = True
                seat.reserved_until = None
                seat.locked_by = None
                seat.save()

        return JsonResponse({"status": "success"})

    except Payment.DoesNotExist:
        return JsonResponse({"status": "failed", "message": "Payment not found"}, status=404)

    except razorpay.errors.SignatureVerificationError:
        return JsonResponse({"status": "failed", "message": "Signature mismatch"}, status=400)

    except Exception as e:
        print("ERROR:", e)
        return JsonResponse({"status": "failed", "message": str(e)}, status=500)

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

def send_email_async(booking_data):
    thread = threading.Thread(target=send_ticket_email, args=(booking_data,))
    thread.start()
    
def create_booking(request):
    booking = Booking.objects.create(...)

    booking_data = {
        "email": booking.user.email,
        "user_name": booking.user.name,
        "movie": booking.movie.name,
        "theater": booking.theater.name,
        "show_time": booking.show_time,
        "seats": ", ".join([s.number for s in booking.seats.all()]),
        "payment_id": booking.payment_id,
    }

    
    send_email_async(booking_data)

    return JsonResponse({"message": "Booking successful"})


def movie_list(request):
    search_query = request.GET.get('search')
    genre = request.GET.get('genre')
    languages = request.GET.getlist('language')
    sort = request.GET.get('sort', 'name')

    movies = Movie.objects.all()

    
    if search_query:
        movies = movies.filter(name__icontains=search_query)

    
    if genre:
        movies = movies.filter(genre__name=genre)

    
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
    ).update(reserved_until=None, locked_by=None)

    seats = Seat.objects.filter(theater=theaters)

    seat_data = []

    for seat in seats:
        if seat.is_booked:
            status = "booked"
        elif seat.reserved_until and seat.reserved_until > timezone.now():
            status = "locked"
        else:
            status = "available"

        seat_data.append({
            "seat": seat,
            "status": status,
            "reserved_until": seat.reserved_until
        })

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
                    if seat.locked_by != request.user:
                        error_seats.append(seat.seat_number)
                        continue

                seat.reserved_until = timezone.now() + timedelta(minutes=2)
                seat.locked_by = request.user
                seat.save()

                booking = Booking.objects.create(
                    user=request.user,
                    seat=seat,
                    movie=theaters.movie,
                    theater=theaters,
                    status="PENDING",
                    amount=200
                )

                created_bookings.append(booking)

        if error_seats:
            error_message = f"The following seats are not available: {', '.join(error_seats)}"
            return render(request, 'movies/seat_selection.html', {
                'theater': theaters,
                'seats': seat_data,
                'error': error_message
            })

        if created_bookings:
            request.session['booking_ids'] = [b.id for b in created_bookings]
            return redirect('create_payment')

    return render(request, 'movies/seat_selection.html', {
        'theater': theaters,
        'seats': seat_data
    })
    
def create_payment(request):
    booking_ids = request.session.get('booking_ids', [])
    bookings = Booking.objects.filter(id__in=booking_ids, status="PENDING")

    if not bookings.exists():
        return redirect('movie_list')

    movie = bookings.first().movie
    theater = bookings.first().theater
    seats = [b.seat.seat_number for b in bookings]
    total_amount = len(bookings) * 200

    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )

    order = client.order.create({
        "amount": int(total_amount * 100),
        "currency": "INR",
        "payment_capture": 1
    })

    with transaction.atomic():
        payment = Payment.objects.create(
            razorpay_order_id=order["id"],
            status="PENDING"
        )

        for booking in bookings:
            if booking.status != "PENDING":
                continue

            booking.payment = payment
            booking.save(update_fields=["payment"])

            seat = booking.seat
            seat.reserved_until = None
            seat.locked_by = None
            seat.save(update_fields=["reserved_until", "locked_by"])

    request.session['booking_ids'] = []
    request.session.modified = True

    return render(request, "movies/payment_page.html", {
        "bookings": bookings,
        "primary_booking": bookings.first(),
        "movie": movie,
        "theater": theater,
        "seats": seats,
        "total_amount": total_amount,
        "order_id": order["id"],
        "razorpay_key": settings.RAZORPAY_KEY_ID,
    })
    
@login_required
@user_passes_test(admin_check)
def admin_dashboard(request):

    data = cache.get("admin_dashboard_data")

    if not data:

        today = timezone.now().date()

        #  Only CONFIRMED bookings
        confirmed_bookings = Booking.objects.filter(status="CONFIRMED")

        # Daily revenue
        daily_revenue = confirmed_bookings.filter(
            booked_at__date=today
        ).aggregate(total=Sum("amount"))["total"] or 0

        # Weekly revenue
        weekly_revenue = confirmed_bookings.filter(
            booked_at__gte=today - timedelta(days=7)
        ).aggregate(total=Sum("amount"))["total"] or 0

        # Monthly revenue
        monthly_revenue = confirmed_bookings.filter(
            booked_at__month=today.month
        ).aggregate(total=Sum("amount"))["total"] or 0

        #  Most popular movies (FIXED)
        popular_movies = confirmed_bookings.values(
            "movie__name"
        ).annotate(
            total_bookings=Count("id")
        ).order_by("-total_bookings")[:5]

        #  Busiest theaters (FIXED)
        busiest_theaters = confirmed_bookings.values(
            "theater__name"
        ).annotate(
            total_bookings=Count("id")
        ).order_by("-total_bookings")[:5]

        #  Peak booking hours (FIXED)
        peak_hours = confirmed_bookings.annotate(
            hour=ExtractHour("booked_at")
        ).values("hour").annotate(
            total=Count("id")
        ).order_by("-total")[:5]

        #  Total confirmed bookings
        total_confirmed = confirmed_bookings.count()

        # Cancellation rate (keep as is, but cleaner)
        total_all = Booking.objects.count()

        cancelled_bookings = Booking.objects.filter(
            status="CANCELLED"
        ).count()

        cancellation_rate = (
            (cancelled_bookings / total_all) * 100
            if total_all > 0 else 0
        )

        data = {
            "daily_revenue": daily_revenue,
            "weekly_revenue": weekly_revenue,
            "monthly_revenue": monthly_revenue,
            "popular_movies": popular_movies,
            "busiest_theaters": busiest_theaters,
            "peak_hours": peak_hours,
            "cancellation_rate": cancellation_rate,
            "total_confirmed": total_confirmed,  
        }

        cache.set("admin_dashboard_data", data, 300)

    return render(request, "admin/dashboard.html", data)