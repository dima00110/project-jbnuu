from django.urls import path

from . import views

app_name = 'schedule'

urlpatterns = [
    path('', views.hub, name='hub'),
    # кабинеты по этажам (справочная, открыта всем вошедшим)
    path('floors/', views.floor_guide, name='floor_guide'),
    # специальности
    path('specialties/', views.specialty_list, name='specialty_list'),
    path('specialties/new/', views.specialty_create, name='specialty_create'),
    path('specialties/<int:pk>/edit/', views.specialty_edit, name='specialty_edit'),
    # кабинеты
    path('cabinets/', views.cabinet_list, name='cabinet_list'),
    path('cabinets/new/', views.cabinet_create, name='cabinet_create'),
    path('cabinets/<int:pk>/edit/', views.cabinet_edit, name='cabinet_edit'),
    # врачи
    path('doctors/', views.doctor_list, name='doctor_list'),
    path('doctors/new/', views.doctor_create, name='doctor_create'),
    path('doctors/<int:pk>/edit/', views.doctor_edit, name='doctor_edit'),
    # расписание
    path('work-schedules/', views.workschedule_list, name='workschedule_list'),
    path('work-schedules/new/', views.workschedule_create, name='workschedule_create'),
    path('work-schedules/<int:pk>/edit/', views.workschedule_edit, name='workschedule_edit'),
]
