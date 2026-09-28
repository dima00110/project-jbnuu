"""Отчёты: загрузка врачей, неявки, поток пациентов за период."""
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import Roles, has_role
from apps.appointments.models import Appointment
from apps.schedule.models import Doctor

REPORT_ROLES = (Roles.ADMINISTRATOR, Roles.MANAGEMENT, Roles.DOCTOR)
ALL_DOCTORS_ROLES = (Roles.ADMINISTRATOR, Roles.MANAGEMENT)


def _parse_period(request):
    """Период ?from=YYYY-MM-DD&to=YYYY-MM-DD, по умолчанию 7 дней."""
    today = timezone.localdate()

    def parse(raw, default):
        try:
            return datetime.strptime(raw, '%Y-%m-%d').date() if raw else default
        except (TypeError, ValueError):
            return default

    date_from = parse(request.GET.get('from'), today - timedelta(days=6))
    date_to = parse(request.GET.get('to'), today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def _doctor_scope(request):
    """
    Определяет врача для фильтрации отчёта:
    - суперпольз./администратор/руководство — все врача (?doctor= опционально),
      селектор фильтра доступен (can_pick=True);
    - врач — жёстко только свой профиль (object-level, can_pick=False).
    Возвращает (doctor_or_None, can_pick, error):
    - can_pick — показывать ли селектор фильтра по врачам;
    - error=True — врач без профиля (redirect на дашборд).
    """
    user = request.user
    if user.is_superuser or has_role(user, *ALL_DOCTORS_ROLES):
        doctor_id = request.GET.get('doctor')
        doctor = None
        if doctor_id and doctor_id.isdigit():
            doctor = Doctor.objects.filter(pk=doctor_id).first()
        return doctor, True, False

    # роль doctor — только своя очередь/свои цифры
    profile = getattr(user, 'doctor_profile', None)
    if profile is None:
        messages.error(request, 'У учётной записи нет профиля врача.')
        return None, False, True
    return profile, False, False


@login_required
@role_required(*REPORT_ROLES)
def reports_hub(request):
    """Хаб отчётов: форма периода и ссылки на три отчёта."""
    date_from, date_to = _parse_period(request)
    doctor, can_pick, error = _doctor_scope(request)
    if error:
        return redirect('dashboard')
    period = f'?from={date_from:%Y-%m-%d}&to={date_to:%Y-%m-%d}'
    context = {
        'date_from': date_from,
        'date_to': date_to,
        'doctor': doctor,
        'can_pick': can_pick,
        'period': period,
        'doctors': Doctor.objects.filter(is_active=True).select_related('user'),
    }
    return render(request, 'reports/hub.html', context)


@login_required
@role_required(*REPORT_ROLES)
def report_load(request):
    """Загрузка врачей: количество записей по статусам и % за период."""
    date_from, date_to = _parse_period(request)
    doctor, can_pick, error = _doctor_scope(request)
    if error:
        return redirect('dashboard')

    qs = Appointment.objects.filter(
        visit_date__range=(date_from, date_to),
    )
    if doctor:
        qs = qs.filter(doctor=doctor)

    rows = list(
        qs.values('doctor_id')
        .annotate(
            total=Count('id'),
            booked=Count('id', filter=Q(status__in=('booked', 'confirmed'))),
            done=Count('id', filter=Q(status='done')),
            no_show=Count('id', filter=Q(status='no_show')),
            cancelled=Count(
                'id',
                filter=Q(status__startswith='cancelled'),
            ),
        )
        .order_by('doctor_id')
    )
    doctors = {
        d.pk: d
        for d in Doctor.objects.filter(
            pk__in=[r['doctor_id'] for r in rows],
        ).select_related('user', 'specialty', 'cabinet')
    }
    for r in rows:
        d = doctors.get(r['doctor_id'])
        r['doctor'] = d
        # % загрузки: фактические записи без учёта «потенциала» слотов
        r['load_pct'] = (
            round(100 * (r['booked'] + r['done'] + r['no_show']) / r['total'])
            if r['total'] else 0
        )

    context = {
        'date_from': date_from,
        'date_to': date_to,
        'doctor': doctor,
        'rows': rows,
        'can_pick': can_pick,
        'doctors': Doctor.objects.filter(is_active=True).select_related('user'),
    }
    return render(request, 'reports/load.html', context)


@login_required
@role_required(*REPORT_ROLES)
def report_no_shows(request):
    """Неявки за период: список визитов no_show + счётчик пациента."""
    date_from, date_to = _parse_period(request)
    doctor, can_pick, error = _doctor_scope(request)
    if error:
        return redirect('dashboard')

    qs = Appointment.objects.filter(
        visit_date__range=(date_from, date_to),
        status=Appointment.Status.NO_SHOW,
    ).select_related(
        'patient', 'doctor__user', 'doctor__specialty',
    ).order_by('-visit_date', '-slot_start')
    if doctor:
        qs = qs.filter(doctor=doctor)

    appointments = list(qs)
    counts = dict(
        qs.values('patient_id').annotate(c=Count('id')).values_list(
            'patient_id', 'c',
        ),
    )
    for a in appointments:
        a.patient_no_shows = counts.get(a.patient_id, 0)
    context = {
        'date_from': date_from,
        'date_to': date_to,
        'doctor': doctor,
        'appointments': appointments,
        'counts': counts,
        'can_pick': can_pick,
        'doctors': Doctor.objects.filter(is_active=True).select_related('user'),
    }
    return render(request, 'reports/no_shows.html', context)


@login_required
@role_required(*REPORT_ROLES)
def report_flow(request):
    """Поток пациентов по дням: записано/завершено/неявки/отмены + CSS-график."""
    date_from, date_to = _parse_period(request)
    doctor, can_pick, error = _doctor_scope(request)
    if error:
        return redirect('dashboard')

    qs = Appointment.objects.filter(visit_date__range=(date_from, date_to))
    if doctor:
        qs = qs.filter(doctor=doctor)

    by_day = {
        r['visit_date']: r
        for r in qs.values('visit_date')
        .annotate(
            total=Count('id'),
            booked=Count('id', filter=Q(status__in=('booked', 'confirmed'))),
            done=Count('id', filter=Q(status='done')),
            no_show=Count('id', filter=Q(status='no_show')),
            cancelled=Count(
                'id',
                filter=Q(status__startswith='cancelled'),
            ),
        )
    }
    days = []
    day = date_from
    while day <= date_to:
        r = by_day.get(day, {
            'total': 0, 'booked': 0, 'done': 0, 'no_show': 0,
            'cancelled': 0,
        })
        r['date'] = day
        days.append(r)
        day += timedelta(days=1)
    peak = max((r['total'] for r in days), default=0)
    for r in days:
        r['bar_pct'] = round(100 * r['total'] / peak) if peak else 0

    context = {
        'date_from': date_from,
        'date_to': date_to,
        'doctor': doctor,
        'days': days,
        'peak': peak,
        'can_pick': can_pick,
        'doctors': Doctor.objects.filter(is_active=True).select_related('user'),
    }
    return render(request, 'reports/flow.html', context)
