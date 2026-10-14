"""Публичные маршруты записи (без входа), подключаются в config/urls.py."""
from django.urls import path

from . import views

urlpatterns = [
    path('request/', views.public_request, name='public_request'),
]
