from django.shortcuts import redirect, render
from django.utils import timezone

from apps.appointments.models import Appointment
from apps.patients.models import Patient
from apps.patients.services import find_patient_by_code
from apps.queue.models import QueueTicket

from .roles import user_roles


def dashboard(request):
    """Главная страница: анонимам — публичная точка входа для пациентов,
    вошедшим — дашборд регистратуры."""
    if not request.user.is_authenticated:
        # Блок «Мои записи»: ввод кода из заявки → переход на /p/<uuid>/.
        # Вошедшим код не нужен — они получают дашборд как раньше.
        code = (request.GET.get('code') or '').strip()
        if code:
            patient = find_patient_by_code(code)
            if patient is not None:
                return redirect('patient_public', public_id=patient.public_id)
            return render(request, 'landing.html', {
                'code': code,
                'code_error': 'Код не найден. Скопируйте его из заявки '
                              'или возьмите ссылку на талоне.',
            })
        return render(request, 'landing.html')
    context = {
        'roles': user_roles(request.user),
        'patient_count': Patient.objects.filter(is_active=True).count(),
        'today_appointments': Appointment.objects.filter(
            visit_date=timezone.localdate(),
            status__in=Appointment.ACTIVE_STATUSES,
        ).count(),
        'queue_waiting': QueueTicket.objects.filter(
            visit_date=timezone.localdate(),
            status=QueueTicket.Status.WAITING,
        ).count(),
    }
    return render(request, 'dashboard.html', context)
