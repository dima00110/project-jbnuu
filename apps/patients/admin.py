from django.contrib import admin

from .models import InsurancePolicy, Patient


class InsurancePolicyInline(admin.TabularInline):
    model = InsurancePolicy
    extra = 0


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'birth_date', 'gender', 'phone', 'snils', 'is_active')
    list_filter = ('is_active', 'gender')
    search_fields = ('last_name', 'first_name', 'patronymic', 'phone', 'snils')
    inlines = (InsurancePolicyInline,)


@admin.register(InsurancePolicy)
class InsurancePolicyAdmin(admin.ModelAdmin):
    list_display = ('patient', 'policy_type', 'number', 'valid_from', 'valid_to')
    list_filter = ('policy_type',)
    search_fields = ('number', 'patient__last_name')
