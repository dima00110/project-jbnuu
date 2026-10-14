"""Публичные маршруты пациентов (без входа), подключаются в config/urls.py."""
from django.urls import path

from . import views

urlpatterns = [
    path('p/<uuid:public_id>/', views.patient_public, name='patient_public'),
]
