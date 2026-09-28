"""URL-маршруты проекта «Регистратура»."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    # Встроенные представления аутентификации (login/logout/password)
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('apps.accounts.urls')),
    path('', include('apps.schedule.public_urls')),
    path('patients/', include('apps.patients.urls')),
    path('schedule/', include('apps.schedule.urls')),
    path('appointments/', include('apps.appointments.urls')),
    path('queue/', include('apps.queue.urls')),
    path('reports/', include('apps.reports.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
