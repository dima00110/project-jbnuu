"""URL-маршруты проекта «Регистратура»."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    # Встроенные представления аутентификации (login/logout/password)
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('apps.accounts.urls')),
    path('patients/', include('apps.patients.urls')),
    path('schedule/', include('apps.schedule.urls')),
    path('appointments/', include('apps.appointments.urls')),
    path('queue/', include('apps.queue.urls')),
]
