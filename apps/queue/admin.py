from django.contrib import admin

from .models import QueueTicket


@admin.register(QueueTicket)
class QueueTicketAdmin(admin.ModelAdmin):
    list_display = ('number', 'visit_date', 'doctor', 'status', 'appointment')
    list_filter = ('status', 'visit_date')
    search_fields = ('appointment__patient__last_name', 'doctor__user__last_name')
    readonly_fields = ('called_at', 'started_at', 'finished_at', 'created_at')
