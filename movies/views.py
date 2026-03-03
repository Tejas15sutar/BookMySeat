from django.shortcuts import render , redirect , get_object_or_404
from .models import Movie,Theater,Seat,Booking
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse


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

def movie_list(request):
    search_query = request.GET.get('search')
    if search_query:
        movies = Movie.objects.filter(name__icontains=search_query)
    else:
        movies = Movie.objects.all()
    return render(request, 'movies/movie_list.html',{'movies':movies})

def movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    return render(request, 'movies/movie_detail.html', {'movie': movie})

def theater_list(request,movie_id):
    movie = get_object_or_404(Movie,id = movie_id)
    theater = Theater.objects.filter(movie=movie)
    return render(request, 'movies/theater_list.html',{'movie':movie,'theaters':theater})

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
            for seat_id in selected_seats:

                seat = Seat.objects.select_for_update().get(
                    id=seat_id,
                    theater=theaters
                )

                
                if seat.is_booked:
                    error_seats.append(seat.seat_number)
                    continue

                
                if seat.reserved_until and seat.reserved_until > timezone.now():
                    error_seats.append(seat.seat_number)
                    continue

                
                seat.is_booked = True
                seat.reserved_until = None
                seat.save()

                Booking.objects.create(
                    user=request.user,
                    seat=seat,
                    movie=theaters.movie,
                    theater=theaters
                )

        if error_seats:
            error_message = f"The following seats are not available: {', '.join(error_seats)}"
            return render(request, 'movies/seat_selection.html', {
                'theater': theaters,
                'seats': seats,
                'error': error_message
            })

        return redirect('profile')

    return render(request, 'movies/seat_selection.html', {
        'theater': theaters,
        'seats': seats
    })