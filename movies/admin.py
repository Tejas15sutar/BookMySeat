from django.contrib import admin
from .models import Movie, Theater, Seat, Booking

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['name','rating','cast','description']


@admin.register(Theater)
class TheaterAdmin(admin.ModelAdmin):
    list_display = ['name','movie','time','rows','seats_per_row']

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        rows = obj.rows
        seats_per_row = obj.seats_per_row

        for row in range(rows):
            row_letter = chr(65 + row)   # A, B, C...

            for seat_num in range(1, seats_per_row + 1):
                seat_number = f"{row_letter}{seat_num}"

                Seat.objects.get_or_create(
                    theater=obj,
                    seat_number=seat_number
                )


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ['theater','seat_number','is_booked']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['user','seat','movie','theater','booked_at']