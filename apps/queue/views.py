from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.accounts.decorators import role_required
from apps.accounts.roles import Roles, has_role
from apps.appointments.models import Appointment
from apps.patients.models import InsurancePolicy
from apps.schedule.models import Doctor

from .models import QueueTicket

QUEUE_READ = (Roles.REGISTRAR, Roles.ADMINISTRATOR, Roles.MANAGEMENT, Roles.DOCTOR)
QUEUE_WRITE = (Roles.REGISTRAR, Roles.ADMINISTRATOR)
CABINET = (Roles.DOCTOR, Roles.ADMINISTRATOR)


def _parse_date(raw, default=None):
    try:
        return (
            timezone.datetime.strptime(raw, '%Y-%m-%d').date() if raw else default
        )
    except (TypeError, ValueError):
        return default


def _can_write(user):
    return user.is_superuser or user.groups.filter(name__in=QUEUE_WRITE).exists()


@login_required
@role_required(*QUEUE_READ)
def queue_list(request):
    """Очередь на дату: все врачи, вызов и перевод талонов."""
    today = timezone.localdate()
    current = _parse_date(request.GET.get('date'), today)
    doctor_id = request.GET.get('doctor')

    qs = QueueTicket.objects.filter(visit_date=current).select_related(
        'doctor__user', 'doctor__specialty', 'appointment__patient',
    )
    if doctor_id and str(doctor_id).isdigit():
        qs = qs.filter(doctor_id=doctor_id)

    context = {
        'date': current,
        'today': today,
        'tickets': qs,
        'doctors': Doctor.objects.filter(is_active=True).select_related('user'),
        'can_write': _can_write(request.user),
        'prev_date': current - timedelta(days=1),
        'next_date': current + timedelta(days=1),
    }
    return render(request, 'queue/queue_list.html', context)


@login_required
@role_required(*QUEUE_WRITE)
def call_next(request):
    """Вызвать следующего пациента врача (POST: doctor, date)."""
    if request.method != 'POST':
        return redirect('queue:queue_list')
    current = _parse_date(request.POST.get('date'), timezone.localdate())
    doctor_id = request.POST.get('doctor')
    doctor = get_object_or_404(Doctor, pk=doctor_id, is_active=True)

    ticket = (
        QueueTicket.objects
        .filter(doctor=doctor, visit_date=current,
                status=QueueTicket.Status.WAITING)
        .select_related('appointment__patient')
        .order_by('number')
        .first()
    )
    if ticket is None:
        messages.warning(request, f'У {doctor.full_name} нет пациентов в очереди.')
    else:
        ticket.status = QueueTicket.Status.CALLED
        ticket.called_at = timezone.now()
        ticket.save()
        messages.success(
            request,
            f'Вызван №{ticket.number} — {ticket.appointment.patient.full_name} '
            f'к {doctor.full_name}.',
        )
    return redirect(f'{reverse("queue:queue_list")}?date={current:%Y-%m-%d}'
                    + (f'&doctor={doctor_id}' if doctor_id else ''))


@login_required
@role_required(*QUEUE_WRITE)
def ticket_action(request, pk):
    """Действия над талоном: call / start / no-show (POST)."""
    if request.method != 'POST':
        return redirect('queue:queue_list')
    ticket = get_object_or_404(
        QueueTicket.objects.select_related(
            'appointment__patient', 'doctor__user',
        ),
        pk=pk,
    )
    action = request.POST.get('action')
    now = timezone.now()
    redirects = f'{reverse("queue:queue_list")}?date={ticket.visit_date:%Y-%m-%d}'

    if action == 'call' and ticket.status == QueueTicket.Status.WAITING:
        ticket.status = QueueTicket.Status.CALLED
        ticket.called_at = now
        ticket.save()
        messages.success(request, f'Вызван №{ticket.number}.')
    elif action == 'start' and ticket.status in (
            QueueTicket.Status.CALLED, QueueTicket.Status.WAITING):
        ticket.status = QueueTicket.Status.WITH_DOCTOR
        ticket.started_at = now
        ticket.save()
        messages.success(request, f'№{ticket.number} принят врачом.')
    elif action == 'no_show' and ticket.is_open:
        ticket.status = QueueTicket.Status.NO_SHOW
        ticket.finished_at = now
        ticket.save()
        appt = ticket.appointment
        appt.status = Appointment.Status.NO_SHOW
        appt.save()
        messages.success(request, f'№{ticket.number}: неявка отмечена.')
    else:
        messages.error(
            request,
            f'Действие «{action}» недоступно для статуса '
            f'«{ticket.get_status_display()}».',
        )
    return redirect(redirects)


@never_cache
def monitor(request):
    """
    Монитор зала ожидания: без навигации, только номера и врачи.
    Доступен без входа (данные обезличены — имён пациентов нет).
    По умолчанию — сегодня, ?date=ГГГГ-ММ-ДД для просмотра.
    """
    today = timezone.localdate()
    current = _parse_date(request.GET.get('date'), today)
    tickets = QueueTicket.objects.filter(visit_date=current).select_related(
        'doctor__user',
    )
    context = {
        'called': [t for t in tickets if t.status == QueueTicket.Status.CALLED],
        'with_doctor': [
            t for t in tickets if t.status == QueueTicket.Status.WITH_DOCTOR
        ],
        'waiting': [
            t for t in tickets if t.status == QueueTicket.Status.WAITING
        ][:12],
        'doctors': sorted({t.doctor.full_name for t in tickets}),
        'date': current,
    }
    return render(request, 'queue/monitor.html', context)


@login_required
@role_required(*CABINET)
def cabinet(request):
    """
    Кабинет врача: своя очередь на дату + действия врача.
    Администратор (и суперпольз.) может открыть чужой кабинет ?doctor=<id>.
    """
    today = timezone.localdate()
    current = _parse_date(request.GET.get('date'), today)

    profile = getattr(request.user, 'doctor_profile', None)
    doctor_id = request.GET.get('doctor')
    is_admin = request.user.is_superuser or has_role(
        request.user, Roles.ADMINISTRATOR,
    )
    if doctor_id and str(doctor_id).isdigit() and is_admin:
        # чужой кабинет открывает только администратор
        doctor = get_object_or_404(Doctor, pk=doctor_id, is_active=True)
    else:
        doctor = profile

    if doctor is None:
        messages.error(
            request,
            'У вашей учётной записи нет профиля врача. '
            'Выберите врача в списке.',
        )
        return redirect('queue:queue_list')

    tickets = QueueTicket.objects.filter(
        visit_date=current, doctor=doctor,
    ).select_related(
        'appointment__patient', 'appointment__created_by',
        'doctor__user', 'doctor__specialty', 'doctor__cabinet',
    )

    # Расширенные данные для карточек пациентов в очереди
    patient_ids = [t.appointment.patient_id for t in tickets]
    policies = {pid: [] for pid in patient_ids}
    for p in InsurancePolicy.objects.filter(patient_id__in=patient_ids):
        policies[p.patient_id].append(p)

    history = {pid: [] for pid in patient_ids}
    for pid in patient_ids:
        history[pid] = list(
            Appointment.objects.filter(
                patient_id=pid,
                status__in=(Appointment.Status.DONE,
                            Appointment.Status.NO_SHOW),
            )
            .select_related('doctor__user', 'doctor__specialty')
            .order_by('-visit_date', '-slot_start')[:5]
        )

    is_admin_view = doctor != profile
    context = {
        'date': current,
        'today': today,
        'doctor': doctor,
        'profile': profile,
        'is_admin_view': is_admin_view,
        'tickets': tickets,
        'policies': policies,
        'history': history,
        'all_doctors': Doctor.objects.filter(is_active=True).select_related('user'),
        'prev_date': current - timedelta(days=1),
        'next_date': current + timedelta(days=1),
        'can_act': True,  # роль прошла role_required(CABINET)
        'is_own': doctor == profile or request.user.is_superuser,
    }
    return render(request, 'queue/cabinet.html', context)


@login_required
@role_required(*CABINET)
def cabinet_action(request, pk):
    """Действия врача над талоном: start / complete (с заметкой) / no-show."""
    if request.method != 'POST':
        return redirect('queue:cabinet')
    ticket = get_object_or_404(
        QueueTicket.objects.select_related(
            'appointment__patient', 'doctor__user',
        ),
        pk=pk,
    )
    profile = getattr(request.user, 'doctor_profile', None)
    # object-level: врач работает только со своей очередью
    if not (request.user.is_superuser or
            has_role(request.user, Roles.ADMINISTRATOR)) and \
            ticket.doctor_id != getattr(profile, 'pk', None):
        messages.error(request, 'Это талон другого врача.')
        return redirect('queue:cabinet')

    action = request.POST.get('action')
    note = (request.POST.get('visit_note') or '').strip()
    appt = ticket.appointment
    redirects = (f'{reverse("queue:cabinet")}'
                 f'?date={ticket.visit_date:%Y-%m-%d}&doctor={ticket.doctor_id}')

    if action == 'start' and ticket.status in (
            QueueTicket.Status.CALLED, QueueTicket.Status.WAITING):
        ticket.status = QueueTicket.Status.WITH_DOCTOR
        ticket.started_at = timezone.now()
        ticket.save()
        messages.success(request, f'№{ticket.number}: приём начат.')
    elif action == 'complete' and ticket.status == QueueTicket.Status.WITH_DOCTOR:
        ticket.status = QueueTicket.Status.COMPLETED
        ticket.finished_at = timezone.now()
        ticket.save()
        appt.status = Appointment.Status.DONE
        appt.visit_note = note
        appt.save()
        messages.success(request, f'№{ticket.number}: приём завершён.')
    elif action == 'no_show' and ticket.is_open:
        ticket.status = QueueTicket.Status.NO_SHOW
        ticket.finished_at = timezone.now()
        ticket.save()
        appt.status = Appointment.Status.NO_SHOW
        appt.save()
        messages.success(request, f'№{ticket.number}: неявка отмечена.')
    else:
        messages.error(
            request,
            f'Действие «{action}» недоступно для статуса '
            f'«{ticket.get_status_display()}».',
        )
    return redirect(redirects)
