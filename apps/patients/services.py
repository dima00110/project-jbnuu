"""Служебные операции над карточками пациентов."""
import re
import uuid as uuid_mod

from .models import Patient

# UUID целиком — с дефисами или без, в любом регистре; ищем внутри строки,
# чтобы принимать и код, и скопированную ссылку /p/<uuid>/
_CODE_RE = re.compile(
    r'[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}'
    r'-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}',
)


def find_patient_by_code(raw):
    """
    Пациент по коду из блока «Мои записи» на главной (без входа).

    Код — это Patient.public_id. Принимается в любом написании:
    с дефисами и без, в разном регистре, целиком или в составе ссылки
    /p/<uuid>/ с талона. Возвращает None, если код не распознан или
    не принадлежит активному пациенту (деактивированные не выдаются —
    как и на самой публичной странице /p/<uuid>/, которая отдаёт 404).
    """
    match = _CODE_RE.search(raw or '')
    if not match:
        return None
    try:
        public_id = uuid_mod.UUID(match.group(0))
    except ValueError:
        return None
    return Patient.objects.filter(public_id=public_id, is_active=True).first()


def find_or_create_patient(cleaned):
    """
    Дедупликация для публичной заявки (/request/).

    Порядок поиска:
    1. СНИЛС (если указан) — включая деактивированные карточки:
       пациент явно обращается, значит, реанимируем её;
    2. ФИО + дата рождения (+ телефон, если совпал по поиску) —
       карточки без СНИЛС не должны плодиться;
    3. иначе — новая карточка.

    Возвращает (patient, created):
      created=True  — карточка создана сейчас;
      created=False — найдена существующая (возможно, реактивирована).
    """
    snils = (cleaned.get('snils') or '').strip()
    if snils:
        patient = Patient.objects.filter(snils=snils).first()
        if patient is not None:
            return _reactivate(patient), False

    # ФИО сравниваем в Python, а не через iexact: SQLite (и многие СУБД)
    # по-регистрно складывает только ASCII, «ИВАНОВ» != «Иванов».
    last = cleaned['last_name'].strip().casefold()
    first = cleaned['first_name'].strip().casefold()
    for patient in Patient.objects.filter(birth_date=cleaned['birth_date']):
        if (patient.last_name.casefold() == last
                and patient.first_name.casefold() == first):
            return _reactivate(patient), False

    patient = Patient(
        last_name=cleaned['last_name'].strip(),
        first_name=cleaned['first_name'].strip(),
        patronymic=(cleaned.get('patronymic') or '').strip(),
        birth_date=cleaned['birth_date'],
        gender=cleaned['gender'],
        snils=snils,
        phone=(cleaned.get('phone') or '').strip(),
        email=(cleaned.get('email') or '').strip(),
    )
    patient.full_clean()  # валидация, в т.ч. уникальность СНИЛС
    patient.save()
    return patient, True


def _reactivate(patient):
    """Пациент обратился сам — деактивированную карточку возвращаем."""
    if not patient.is_active:
        patient.is_active = True
        patient.save(update_fields=['is_active', 'updated_at'])
    return patient
