from django.contrib.auth.forms import AuthenticationForm,PasswordChangeForm
from.forms import UserRegisterForm, UserUpdateForm
from django.shortcuts import render,redirect
from django.contrib.auth import login,authenticate
from django.contrib.auth.decorators import login_required
from movies.models import Movie , Booking
import random
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from .models import EmailOTP
from movies.utils.email import send_otp_email
from django.contrib.auth.models import User


def home(request):
    movies=Movie.objects.all()
    return render(request, 'home.html',{'movies':movies})

def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp(request):
    email = request.POST.get("email")

    if not email:
        return JsonResponse({"error": "Email required"})

    otp = str(generate_otp())

    
    existing = EmailOTP.objects.filter(email=email).first()
    if existing:
        time_diff = timezone.now() - existing.created_at
        if time_diff.seconds < 60:
            return JsonResponse({"error": "Wait 60 seconds before requesting OTP"})

    EmailOTP.objects.filter(email=email).delete()
    EmailOTP.objects.create(email=email, otp=otp)

    send_otp_email(email, otp)

    return JsonResponse({"message": "OTP sent"})


def verify_otp(request):
    email = request.POST.get("email")
    otp = request.POST.get("otp")

    try:
        record = EmailOTP.objects.filter(email=email).latest("created_at")

        # 1. FIRST check expiry
        if timezone.now() - record.created_at > timedelta(minutes=5):
            return JsonResponse({"error": "OTP expired"})

        # 2. THEN check OTP
        if str(record.otp).strip() != str(otp).strip():
            return JsonResponse({"error": "Invalid OTP"})

        # success
        request.session['otp_verified'] = True
        request.session['otp_email'] = email

        return JsonResponse({"message": "Verified"})

    except EmailOTP.DoesNotExist:
        return JsonResponse({"error": "No OTP found"})

def register(request):
    if request.method == 'POST':

        if not request.session.get('otp_verified'):
            return JsonResponse({"error": "Verify OTP first"})

        form = UserRegisterForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data.get('email')

            if email != request.session.get('otp_email'):
                return JsonResponse({"error": "Email mismatch"})

            user = form.save()

            # CLEAR SESSION (important)
            request.session.flush()

            login(request, user)

            return redirect('profile')

    else:
        form = UserRegisterForm()

    return render(request, 'users/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        email = request.POST.get("email")
        password = request.POST.get("password")

        try:
            user_obj = User.objects.get(email=email)
        except User.DoesNotExist:
            user_obj = None

        if user_obj is not None:
            user = authenticate(
                request,
                username=user_obj.username,
                password=password
            )
        else:
            user = None

        if user is not None:
            login(request, user)
            return redirect('/')
        else:
            return render(request, 'users/login.html', {
                'error': 'Invalid email or password'
            })

    return render(request, 'users/login.html')

@login_required
def profile(request):
    bookings = Booking.objects.filter(user=request.user, status="CONFIRMED")

    u_form = UserUpdateForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and u_form.is_valid():
        u_form.save()
        return redirect('profile')

    return render(request, 'users/profile.html', {'u_form': u_form, 'bookings': bookings})

@login_required
def reset_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(user = request.user , data = request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
        
    else:
        form = PasswordChangeForm(user =request.user)
    return render(request,'users/reset_password.html',{'form':form})