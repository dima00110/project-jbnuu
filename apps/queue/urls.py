from django.urls import path

from . import views

app_name = 'queue'

urlpatterns = [
    path('', views.queue_list, name='queue_list'),
    path('call-next/', views.call_next, name='call_next'),
    path('<int:pk>/action/', views.ticket_action, name='ticket_action'),
    path('monitor/', views.monitor, name='monitor'),
    path('cabinet/', views.cabinet, name='cabinet'),
    path('cabinet/<int:pk>/action/', views.cabinet_action, name='cabinet_action'),
]
