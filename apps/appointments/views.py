from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import Roles

from apps.patients.models import Patient
from apps.patients.services import find_or_create_patient
from apps.schedule.models import Doctor, Specialty

from .forms import (
    AppointmentCancelForm, AppointmentCreateForm, AppointmentMoveForm,
    DirectionCreateForm, PatientRequestForm,
)
from .models import Appointment, Direction
from .routing import find_candidates
from .slots import generate_slots

WRITE_ROLES = (Roles.REGISTRAR, Roles.ADMINISTRATOR)
READ_ROLES = (Roles.REGISTRAR, Roles.ADMINISTRATOR, Roles.MANAGEMENT)
DIRECTION_LIST_ROLES = (
    Roles.REGISTRAR, Roles.ADMINISTRATOR, Roles.MANAGEMENT, Roles.DOCTOR,
)
DIRECTION_CREATE_ROLES = (Roles.DOCTOR, Roles.ADMINISTRATOR)


def _is_doctor_only(user):
    """Врач без иных ролей: видит в направлениях только свои."""
    if user.is_superuser:
        return False
    return set(user.groups.values_list('name', flat=True)) == {Roles.DOCTOR}


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
            # пришли из направления — закрываем его этой записью
            raw_dir = request.POST.get('direction')
            if raw_dir and str(raw_dir).isdigit():
                direction = Direction.objects.filter(
                    pk=raw_dir, status=Direction.Status.NEW,
                ).first()
                if direction and direction.patient_id == appt.patient_id:
                    direction.status = Direction.Status.BOOKED
                    direction.appointment = appt
                    direction.save(update_fields=['status', 'appointment'])
                    messages.success(
                        request,
                        f'Направление {direction.number} закрыто записью.',
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

    # направление, из которого пришли («Записать» на списке направлений)
    direction = None
    raw_dir = request.GET.get('direction')
    if raw_dir and str(raw_dir).isdigit():
        direction = Direction.objects.filter(
            pk=raw_dir, status=Direction.Status.NEW,
        ).first()

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
        'direction': direction,
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


# --- Направления к подходящему свободному врачу ---------------------------

@login_required
@role_required(*DIRECTION_LIST_ROLES)
def direction_list(request):
    """
    Входящие направления: регистратор/админ/руководство видят все,
    врач — только созданные им. Для новых направлений на месте
    подбираются кандидаты (routing.find_candidates).
    """
    qs = Direction.objects.select_related(
        'patient', 'specialty', 'from_doctor__user',
        'created_by', 'appointment__doctor__user',
        'appointment__doctor__specialty',
    )
    if _is_doctor_only(request.user):
        profile = getattr(request.user, 'doctor_profile', None)
        qs = qs.filter(from_doctor=profile)
    directions = list(qs)
    for d in directions:
        d.candidates = (
            find_candidates(d.specialty)
            if d.status == Direction.Status.NEW else []
        )
    can_write = request.user.is_superuser or request.user.groups.filter(
        name__in=WRITE_ROLES,
    ).exists()
    return render(request, 'appointments/direction_list.html', {
        'directions': directions,
        'can_write': can_write,
    })


@login_required
@role_required(*DIRECTION_CREATE_ROLES)
def direction_create(request):
    """
    Выписка направления:
    - врач — только по своему приёму (?appointment=<id>), из кабинета;
    - администратор — с карточки пациента (?patient=<id>) или по приёму.
    """
    doctor_only = _is_doctor_only(request.user)
    patient = None
    appt = None
    raw_appt = request.GET.get('appointment') or request.POST.get('appointment')
    if raw_appt and str(raw_appt).isdigit():
        appt = Appointment.objects.select_related(
            'patient', 'doctor',
        ).filter(pk=raw_appt).first()

    if doctor_only:
        profile = getattr(request.user, 'doctor_profile', None)
        if appt is None or profile is None or appt.doctor_id != profile.pk:
            messages.error(
                request, 'Направление можно выписать только по своему приёму.',
            )
            return redirect('queue:cabinet')
        patient = appt.patient
    else:
        raw_patient = request.GET.get('patient') or request.POST.get('patient')
        if raw_patient and str(raw_patient).isdigit():
            patient = Patient.objects.filter(
                pk=raw_patient, is_active=True,
            ).first()
        if patient is None and appt is not None:
            patient = appt.patient
        if patient is None:
            messages.error(request, 'Укажите пациента для направления.')
            return redirect('patients:patient_list')

    if request.method == 'POST':
        form = DirectionCreateForm(request.POST)
        if form.is_valid():
            direction = Direction.objects.create(
                patient=patient,
                specialty=form.cleaned_data['specialty'],
                reason=form.cleaned_data['reason'],
                from_doctor=appt.doctor if appt is not None else None,
                created_by=request.user,
            )
            messages.success(
                request,
                f'Направление {direction.number} отправлено в регистратуру: '
                f'{direction.patient.full_name} → {direction.specialty}.',
            )
            return redirect('appointments:direction_list')
    else:
        form = DirectionCreateForm()

    return render(request, 'appointments/direction_form.html', {
        'form': form, 'patient': patient, 'appt': appt,
    })


@login_required
@role_required(*WRITE_ROLES)
def direction_cancel(request, pk):
    """Отмена направления регистратором/администратором (POST)."""
    direction = get_object_or_404(Direction, pk=pk)
    if request.method != 'POST':
        return redirect('appointments:direction_list')
    if direction.status != Direction.Status.NEW:
        messages.error(
            request,
            f'Направление {direction.number} уже в статусе '
            f'«{direction.get_status_display()}».',
        )
        return redirect('appointments:direction_list')
    direction.status = Direction.Status.CANCELLED
    direction.save(update_fields=['status'])
    messages.success(request, f'Направление {direction.number} отменено.')
    return redirect('appointments:direction_list')


# --- Публичная заявка пациента (без входа) ---------------------------------


def public_request(request):
    """
    Заявка на приём для нового пациента (/request/, без аутентификации).

    Данные формы → карточка пациента (с дедупликацией) + Direction
    в регистратуру (created_by=NULL — маркер «заявка с сайта»).
    Успех — редирект на публичную страницу пациента с баннером
    и подобранными свободными врачами (routing.find_candidates).
    """
    initial = {}
    raw_spec = request.GET.get('specialty')
    if raw_spec and str(raw_spec).isdigit() and Specialty.objects.filter(
        pk=raw_spec, doctors__is_active=True,
    ).exists():
        initial['specialty'] = raw_spec

    if request.method == 'POST':
        form = PatientRequestForm(request.POST)
        # honeypot: бот заполнил скрытое поле — показываем «успех»,
        # ничего не записывая и не выдавая чужие данные
        if form.data.get('website'):
            return render(
                request, 'appointments/request_form.html',
                {'form': None, 'sent': True},
            )
        if form.is_valid():
            patient, created = find_or_create_patient(form.cleaned_data)
            direction = Direction.objects.create(
                patient=patient,
                specialty=form.cleaned_data['specialty'],
                reason=form.cleaned_data['reason'],
                created_by=None,  # NULL = заявка с сайта
            )
            return redirect(
                f"{reverse('patient_public', args=[patient.public_id])}"
                f"?new={direction.pk}&created={int(created)}",
            )
    else:
        form = PatientRequestForm(initial=initial)

    return render(request, 'appointments/request_form.html', {
        'form': form,
        'specialties': Specialty.objects.filter(
            doctors__is_active=True,
        ).distinct().order_by('name'),
    })
