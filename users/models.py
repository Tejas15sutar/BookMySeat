from django.db import models

class Movie(models.Model):
    name = models.CharField(max_length=100)
    release_date = models.DateField()

    def __str__(self):
        return self.name
    
    
class EmailOTP(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email