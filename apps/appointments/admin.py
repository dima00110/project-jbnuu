from django.contrib import admin

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        'visit_date', 'slot_start', 'patient',
        'doctor', 'status', 'created_by',
    )
    list_filter = ('status', 'visit_date', 'visit_type')
    search_fields = (
        'patient__last_name', 'patient__first_name',
        'doctor__user__last_name',
    )
    readonly_fields = ('created_at', 'updated_at')
