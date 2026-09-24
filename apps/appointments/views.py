from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import Roles

from apps.patients.models import Patient
from apps.schedule.models import Doctor, Specialty

from .forms import AppointmentCancelForm, AppointmentCreateForm, AppointmentMoveForm
from .models import Appointment
from .slots import generate_slots

WRITE_ROLES = (Roles.REGISTRAR, Roles.ADMINISTRATOR)
READ_ROLES = (Roles.REGISTRAR, Roles.ADMINISTRATOR, Roles.MANAGEMENT)


@login_required
@role_required(*READ_ROLES)
def day_list(request):
    """Записи на день: ?date=YYYY-MM-DD (по умолчанию — сегодня)."""
    today = timezone.localdate()
    raw = request.GET.get('date')
    try:
        current = (
            timezone.datetime.strptime(raw, '%Y-%m-%d').date() if raw else today
        )
    except ValueError:
        current = today

    qs = Appointment.objects.filter(visit_date=current).select_related(
        'patient', 'doctor__user', 'doctor__specialty',
    )
    doctor_id = request.GET.get('doctor')
    if doctor_id and doctor_id.isdigit():
        qs = qs.filter(doctor_id=doctor_id)

    context = {
        'date': current,
        'appointments': qs,
        'doctors': Doctor.objects.filter(is_active=True).select_related('user'),
        'today': today,
        'can_write': request.user.is_superuser
        or request.user.groups.filter(name__in=WRITE_ROLES).exists(),
        'prev_date': current - timedelta(days=1),
        'next_date': current + timedelta(days=1),
    }
    return render(request, 'appointments/day_list.html', context)


@login_required
@role_required(*WRITE_ROLES)
def booking(request):
    """
    Запись на приём.
    GET: ?patient=<id>&specialty=<id>&doctor=<id>&date=YYYY-MM-DD — сетка слотов
    POST: создание записи (AppointmentCreateForm)
    """
    today = timezone.localdate()
    patient = None
    patient_id = request.GET.get('patient') or request.POST.get('patient')
    if patient_id and str(patient_id).isdigit():
        patient = Patient.objects.filter(pk=patient_id, is_active=True).first()

    if request.method == 'POST':
        form = AppointmentCreateForm(request.POST)
        if form.is_valid():
            appt = form.save(commit=False)
            appt.created_by = request.user
            appt.save()
            messages.success(
                request,
                f'Запись создана: {appt.patient.full_name} → '
                f'{appt.doctor.full_name}, {appt.visit_date:%d.%m.%Y} {appt.slot_start:%H:%M}.',
            )
            from django.http import HttpResponseRedirect
            from django.urls import reverse
            return HttpResponseRedirect(
                f"{reverse('appointments:day_list')}?date={appt.visit_date:%Y-%m-%d}",
            )
        # при ошибке — показать ту же страницу со слотами
        messages.error(request, 'Не удалось создать запись. Проверьте форму.')
    else:
        form = AppointmentCreateForm(initial={'patient': patient_id})

    specialty_id = request.GET.get('specialty')
    doctor_id = request.GET.get('doctor')
    raw_date = request.GET.get('date')
    try:
        current = (
            timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
            if raw_date else today
        )
    except ValueError:
        current = today

    specialties = Specialty.objects.filter(doctors__is_active=True).distinct()
    doctors = Doctor.objects.filter(is_active=True).select_related(
        'user', 'specialty', 'cabinet',
    )
    if specialty_id and str(specialty_id).isdigit():
        doctors = doctors.filter(specialty_id=specialty_id)
    if doctor_id and str(doctor_id).isdigit():
        doctors = doctors.filter(pk=doctor_id)

    doctor = doctors.first() if doctor_id and str(doctor_id).isdigit() else None
    slots = generate_slots(doctor, current) if doctor else []

    context = {
        'form': form,
        'patient': patient,
        'specialties': specialties,
        'doctors': doctors,
        'doctor': doctor,
        'date': current,
        'slots': slots,
        'today': today,
        'selected_specialty': specialty_id,
        'selected_doctor': doctor_id,
    }
    return render(request, 'appointments/booking.html', context)


@login_required
@role_required(*READ_ROLES)
def appointment_ticket(request, pk):
    """Талон: страница форматирования под печать браузера."""
    appt = get_object_or_404(
        Appointment.objects.select_related(
            'patient', 'doctor__user', 'doctor__specialty', 'doctor__cabinet',
        ),
        pk=pk,
    )
    return render(request, 'appointments/ticket.html', {'appt': appt})


@login_required
@role_required(*READ_ROLES)
def appointment_detail(request, pk):
    appt = get_object_or_404(
        Appointment.objects.select_related(
            'patient', 'doctor__user', 'doctor__specialty', 'doctor__cabinet',
            'created_by',
        ),
        pk=pk,
    )
    can_write = request.user.is_superuser or request.user.groups.filter(
        name__in=WRITE_ROLES,
    ).exists()
    return render(request, 'appointments/appointment_detail.html', {
        'appt': appt, 'can_write': can_write,
        'cancel_form': AppointmentCancelForm(),
    })


@login_required
@role_required(*WRITE_ROLES)
def appointment_move(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)
    if not appt.is_active:
        messages.error(request, 'Переносить можно только активную запись.')
        return redirect('appointments:appointment_detail', pk=pk)

    if request.method == 'POST':
        form = AppointmentMoveForm(request.POST)
        form.appointment = appt
        if form.is_valid():
            old = f'{appt.visit_date:%d.%m.%Y} {appt.slot_start:%H:%M}'
            appt.visit_date = form.cleaned_data['visit_date']
            appt.slot_start = form.cleaned_data['slot_start']
            appt.save()
            messages.success(
                request,
                f'Запись перенесена: {old} → '
                f'{appt.visit_date:%d.%m.%Y} {appt.slot_start:%H:%M}.',
            )
            return redirect('appointments:appointment_detail', pk=pk)
        messages.error(request, 'Не удалось перенести запись.')
    else:
        form = AppointmentMoveForm(initial={
            'visit_date': appt.visit_date, 'slot_start': appt.slot_start,
        })
        form.appointment = appt

    raw_date = request.GET.get('date')
    try:
        current = (
            timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
            if raw_date else appt.visit_date
        )
    except ValueError:
        current = appt.visit_date

    slots = generate_slots(appt.doctor, current, exclude_pk=appt.pk)
    return render(request, 'appointments/move.html', {
        'appt': appt, 'form': form, 'date': current, 'slots': slots,
        'today': timezone.localdate(),
    })


@login_required
@role_required(*WRITE_ROLES)
def appointment_cancel(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)
    if request.method != 'POST':
        return redirect('appointments:appointment_detail', pk=pk)
    if not appt.is_active:
        messages.error(request, 'Запись уже не активна.')
        return redirect('appointments:appointment_detail', pk=pk)
    form = AppointmentCancelForm(request.POST)
    if form.is_valid():
        appt.status = Appointment.Status.CANCELLED_REGISTRAR
        appt.cancel_reason = form.cleaned_data['reason']
        appt.save()
        messages.success(
            request,
            f'Запись отменена: {appt.patient.full_name}, '
            f'{appt.visit_date:%d.%m.%Y} {appt.slot_start:%H:%M}.',
        )
    else:
        messages.error(request, 'Укажите причину отмены.')
    return redirect('appointments:appointment_detail', pk=pk)


@login_required
@role_required(*WRITE_ROLES)
def set_status(request, pk):
    """Подтверждение / неявка / завершение — переключение статуса."""
    appt = get_object_or_404(Appointment, pk=pk)
    if request.method != 'POST':
        return redirect('appointments:appointment_detail', pk=pk)
    action = request.POST.get('action')
    transitions = {
        'confirm': (Appointment.Status.BOOKED, Appointment.Status.CONFIRMED, 'подтверждена'),
        'noshow': (Appointment.Status.CONFIRMED, Appointment.Status.NO_SHOW, 'отмечена неявка'),
        'done': (Appointment.Status.CONFIRMED, Appointment.Status.DONE, 'приём завершён'),
    }
    if action not in transitions:
        messages.error(request, 'Неизвестное действие.')
        return redirect('appointments:appointment_detail', pk=pk)
    from_status, to_status, verb = transitions[action]
    if appt.status != from_status:
        messages.error(
            request,
            f'Действие недоступно: статус «{appt.get_status_display()}».',
        )
    else:
        appt.status = to_status
        appt.save()
        messages.success(request, f'Запись {verb}.')
    return redirect('appointments:appointment_detail', pk=pk)
