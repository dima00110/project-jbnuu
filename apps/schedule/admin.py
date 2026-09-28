from django.contrib import admin

from .models import Cabinet, Department, Doctor, Specialty, WorkSchedule


@admin.register(Specialty)
class SpecialtyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')


@admin.register(Cabinet)
class CabinetAdmin(admin.ModelAdmin):
    list_display = ('number', 'floor', 'building')
    search_fields = ('number',)


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'specialty', 'cabinet', 'is_active')
    list_filter = ('is_active', 'specialty')
    search_fields = ('user__last_name', 'user__first_name', 'user__username')


@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    list_display = ('doctor', 'weekday', 'start_time', 'end_time', 'slot_minutes')
    list_filter = ('weekday',)
