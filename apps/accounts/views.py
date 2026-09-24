from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.patients.models import Patient

from .roles import user_roles


@login_required
def dashboard(request):
    """Главная страница после входа — дашборд регистратуры."""
    context = {
        'roles': user_roles(request.user),
        'patient_count': Patient.objects.filter(is_active=True).count(),
    }
    return render(request, 'dashboard.html', context)
