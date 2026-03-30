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


def home(request):
    movies=Movie.objects.all()
    return render(request, 'home.html',{'movies':movies})

def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp(request):
    email = request.POST.get("email")

    otp = generate_otp()

    EmailOTP.objects.filter(email=email).delete()
    EmailOTP.objects.create(email=email, otp=otp)

    send_otp_email(email, otp)

    return JsonResponse({"message": "OTP sent"})


def verify_otp(request):
    email = request.POST.get("email")
    otp = request.POST.get("otp")

    try:
        record = EmailOTP.objects.filter(email=email).latest("created_at")

        if timezone.now() - record.created_at > timedelta(minutes=5):
            return JsonResponse({"error": "OTP expired"})

        if record.otp == otp:
            request.session['otp_verified'] = True   
            request.session['otp_email'] = email     
            return JsonResponse({"message": "Verified"})
        else:
            return JsonResponse({"error": "Invalid OTP"})

    except:
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

            form.save()

            
            request.session.pop('otp_verified', None)
            request.session.pop('otp_email', None)

            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')

            user = authenticate(username=username, password=password)
            login(request, user)

            return redirect('profile')

    else:
        form = UserRegisterForm()

    return render(request, 'users/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data = request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request,user)
            return redirect('/')
        
    else:
        form = AuthenticationForm()
    return render(request,'users/login.html',{'form':form})

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