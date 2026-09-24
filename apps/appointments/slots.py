"""Генерация свободных/занятых слотов по расписанию врача."""
from datetime import datetime, timedelta

from django.utils import timezone

from apps.schedule.models import WorkSchedule

from .models import Appointment


def generate_slots(doctor, date, exclude_pk=None):
    """
    Возвращает отсортированный список слотов врача на дату:
    [{'time': time, 'busy': bool, 'past': bool}, ...]
    exclude_pk — ID записи, которую не считать занятой (для переноса).
    """
    schedules = WorkSchedule.objects.filter(
        doctor=doctor, weekday=date.isoweekday(),
    )
    busy = set(
        Appointment.objects.filter(
            doctor=doctor, visit_date=date,
            status__in=Appointment.ACTIVE_STATUSES,
        )
        .exclude(pk=exclude_pk)
        .values_list('slot_start', flat=True)
    )

    now = timezone.localtime()
    slots, seen = [], set()
    for ws in schedules:
        if ws.valid_from and date < ws.valid_from:
            continue
        if ws.valid_to and date > ws.valid_to:
            continue
        current = datetime.combine(date, ws.start_time)
        end = datetime.combine(date, ws.end_time)
        step = timedelta(minutes=ws.slot_minutes)
        while current + step <= end:
            t = current.time()
            if t not in seen:
                seen.add(t)
                slots.append({
                    'time': t,
                    'busy': t in busy,
                    'past': date < now.date() or
                            (date == now.date() and t <= now.time()),
                })
            current += step

    slots.sort(key=lambda s: s['time'])
    return slots
