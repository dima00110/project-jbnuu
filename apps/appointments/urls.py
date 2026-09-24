from django.urls import path

from . import views

app_name = 'appointments'

urlpatterns = [
    path('', views.day_list, name='day_list'),
    path('booking/', views.booking, name='booking'),
    path('<int:pk>/', views.appointment_detail, name='appointment_detail'),
    path('<int:pk>/ticket/', views.appointment_ticket, name='appointment_ticket'),
    path('<int:pk>/move/', views.appointment_move, name='appointment_move'),
    path('<int:pk>/cancel/', views.appointment_cancel, name='appointment_cancel'),
    path('<int:pk>/status/', views.set_status, name='set_status'),
]
