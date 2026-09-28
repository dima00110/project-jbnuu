"""Публичные маршруты врачей (без входа), подключаются в config/urls.py."""
from django.urls import path

from . import views

urlpatterns = [
    path('doctors/', views.doctor_directory, name='doctor_directory'),
    path('doctors/<int:pk>/', views.doctor_card, name='doctor_card'),
]
