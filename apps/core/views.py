
from django.shortcuts import render


def home(request):
    """
    Render the main Free Fire Arena homepage.
    """
    return render(request, "pages/home.html")
