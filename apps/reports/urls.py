from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.reports_hub, name='hub'),
    path('load/', views.report_load, name='load'),
    path('no-shows/', views.report_no_shows, name='no_shows'),
    path('flow/', views.report_flow, name='flow'),
]
