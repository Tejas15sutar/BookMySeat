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
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            order_id = data.get("order_id")
            payment_id = data.get("payment_id")
            signature = data.get("signature")

            client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )

           
            client.utility.verify_payment_signature({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature
            })

            payment = Payment.objects.select_for_update().get(
                razorpay_order_id=order_id,
                status="PENDING"
            )

            with transaction.atomic():

                payment.razorpay_payment_id = payment_id
                payment.status = "SUCCESS"
                payment.save(update_fields=['razorpay_payment_id', 'status'])

                for booking in payment.bookings.select_related('seat').all():
                    booking.status = "CONFIRMED"
                    booking.save(update_fields=['status'])

                    seat = booking.seat
                    seat.is_booked = True
                    seat.reserved_until = None
                    seat.locked_by = None
                    seat.save(update_fields=['is_booked', 'reserved_until', 'locked_by'])

            return JsonResponse({"status": "success"})

        except Exception as e:
            print("ERROR:", e)
            return JsonResponse({"status": "failed"})

    return JsonResponse({"status": "invalid request"})
    
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

def send_email_async(data):
    send_ticket_email(data)
@transaction.atomic
def confirm_booking(request, seat_id):
    try:
        seat = Seat.objects.select_for_update().get(id=seat_id)

        if seat.reserved_until and seat.reserved_until > timezone.now():
            seat.is_booked = True
            seat.reserved_until = None
            seat.save()
            
            booking_data = {
                "booking": {"id": seat.id},
                "movie": {"name": seat.theater.movie.name if hasattr(seat.theater, 'movie') else "Movie"},
                "theater": {"name": seat.theater.name},
                "seats": seat.seat_number,
                "payment_id": "PAY123456",  
                "email": request.user.email if request.user.is_authenticated else "test@gmail.com"
            }

            
            threading.Thread(target=send_email_async, args=(booking_data,)).start()

            return JsonResponse({"message": "Seat booked successfully"})

        return JsonResponse({"error": "Reservation expired"}, status=400)

    except Seat.DoesNotExist:
        return JsonResponse({"error": "Seat not found"}, status=404)


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
                    status="PENDING"
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

    # create Payment and link all bookings
    payment = Payment.objects.create(razorpay_order_id=order["id"])
    payment.bookings.set(bookings)
    payment.save()

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