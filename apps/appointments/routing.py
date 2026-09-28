"""Подбор подходящих свободных врачей для направления.

Критерии (в порядке значимости):
1. ближайший свободный слот в горизонте HORIZON_DAYS дней;
2. загрузка сегодня (доля занятых слотов);
3. этаж → номер кабинета → ФИО (вес кабинета/этажа как тай-брейкер).
"""
from datetime import datetime, timedelta

from django.utils import timezone

from apps.schedule.models import Doctor

from .slots import generate_slots

HORIZON_DAYS = 7
CANDIDATE_LIMIT = 5


def _cabinet_key(doctor):
    """(этаж, число кабинета) — для сортировки, нечисловые номера в конец."""
    cab = doctor.cabinet
    if cab is None:
        return (999, 999)
    try:
        number = int(cab.number)
    except (TypeError, ValueError):
        number = 999
    return (cab.floor, number)


def find_candidates(specialty, days=HORIZON_DAYS, limit=CANDIDATE_LIMIT):
    """
    Возвращает список карточек-кандидатов активных врачей специальности:
    [{'doctor', 'first_date', 'first_time', 'load_pct', 'busy_today',
      'total_today'}, ...] — отсортированных по рейтингу, не длиннее limit.
    Врачи без свободных слотов в горизонте исключаются.
    """
    today = timezone.localdate()
    doctors = Doctor.objects.filter(
        specialty=specialty, is_active=True,
    ).select_related('user', 'cabinet', 'department')

    result = []
    for doctor in doctors:
        # ближайший свободный слот (сегодня → +days)
        first_dt = None
        for offset in range(days):
            day = today + timedelta(days=offset)
            free = [s for s in generate_slots(doctor, day)
                    if not s['busy'] and not s['past']]
            if free:
                first_dt = datetime.combine(day, free[0]['time'])
                break
        if first_dt is None:
            continue

        # загрузка сегодня: занятые / все слоты дня (нет расписания → 0%)
        today_slots = generate_slots(doctor, today)
        total = len(today_slots)
        busy = sum(1 for s in today_slots if s['busy'])
        load_pct = round(busy * 100 / total) if total else 0
        result.append({
            'doctor': doctor,
            'first_date': first_dt.date(),
            'first_time': first_dt.time(),
            'load_pct': load_pct,
            'busy_today': busy,
            'total_today': total,
            '_sort': (first_dt, load_pct, *_cabinet_key(doctor),
                      doctor.full_name),
        })

    result.sort(key=lambda c: c.pop('_sort'))
    return result[:limit]
