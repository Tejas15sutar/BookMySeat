from django.urls import path
from . import views
urlpatterns=[
    path('',views.movie_list,name='movie_list'),
    path('movie/<int:movie_id>/', views.movie_detail, name='movie_detail'),
    path('<int:movie_id>/theaters',views.theater_list,name='theater_list'),
    path('theater/<int:theater_id>/seats/book/',views.book_seats,name='book_seats'),
    path('confirm-booking/<int:seat_id>/', views.confirm_booking, name='confirm_booking'),
    path("create-payment/<int:booking_id>/", views.create_payment, name="create_payment"),
    path("payment/webhook/", views.payment_webhook),
]