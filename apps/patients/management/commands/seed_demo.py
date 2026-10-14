"""
Демо-данные для пилота: пользователи с ролями, пациенты с полисами,
справочники, расписание приёма и записи на сегодня/завтра.

Использование:
    python manage.py seed_demo            # добавить недостающие демо-данные
    python manage.py seed_demo --reset    # удалить демо-данные и создать заново

Метки демо-данных: пациенты — '[demo]' в notes, записи — '[demo]' в comment.
Пароли демо-пользователей при каждом запуске выставляются заново.
"""
from datetime import date, datetime, timedelta

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.accounts.roles import Roles
from apps.appointments.models import Appointment, Direction
from apps.appointments.slots import generate_slots
from apps.patients.models import InsurancePolicy, Patient
from apps.schedule.models import Cabinet, Department, Doctor, Specialty, WorkSchedule

DEMO_TAG = '[demo]'

# (username, password, role, full_name «Имя Фамилия»)
DEMO_USERS = [
    ('registrar1', 'registrar12345', Roles.REGISTRAR, 'Ирина Смирнова'),
    ('registrar2', 'registrar12345', Roles.REGISTRAR, 'Алексей Ковалёв'),
    ('doctor1', 'doctor12345', Roles.DOCTOR, 'Дмитрий Орлов'),
    ('doctor2', 'doctor12345', Roles.DOCTOR, 'Азиз Каримов'),
    ('doctor3', 'doctor12345', Roles.DOCTOR, 'Дилшод Ахмедов'),
    ('manager', 'manager12345', Roles.MANAGEMENT, 'Главный сотрудник'),
    # расширение пилота: по врачу на каждую специальность
    ('doctor4', 'doctor12345', Roles.DOCTOR, 'Рустам Ганиев'),
    ('doctor5', 'doctor12345', Roles.DOCTOR, 'Алия Хасанова'),
    ('doctor6', 'doctor12345', Roles.DOCTOR, 'Тимур Юсупов'),
    ('doctor7', 'doctor12345', Roles.DOCTOR, 'Шухрат Сафаров'),
    ('doctor8', 'doctor12345', Roles.DOCTOR, 'Марат Ибраимов'),
    ('doctor9', 'doctor12345', Roles.DOCTOR, 'Жасур Камолов'),
    ('doctor10', 'doctor12345', Roles.DOCTOR, 'Малика Рахимова'),
    ('doctor11', 'doctor12345', Roles.DOCTOR, 'Олег Мирзоев'),
    ('doctor12', 'doctor12345', Roles.DOCTOR, 'Зульфия Носирова'),
    ('doctor13', 'doctor12345', Roles.DOCTOR, 'Азиз Толипов'),
    ('doctor14', 'doctor12345', Roles.DOCTOR, 'Ирина Белова'),
    ('doctor15', 'doctor12345', Roles.DOCTOR, 'Фаррух Собиров'),
]

# Поля пациента + список полисов: (тип, номер, страхователь, с, по)
DEMO_PATIENTS = [
    dict(
        last_name='Соколова', first_name='Мария', patronymic='Александровна',
        birth_date=date(1990, 5, 20), gender='F', snils='100-200-300 40',
        phone='+998 90 555-11-22', address='Ташкент, Чиланзар',
        notes=f'{DEMO_TAG} участница диспансеризации',
        policies=[('OMS', 'AB000001', 'УВС ОМС', date(2024, 1, 1), date(2027, 12, 31))],
    ),
    dict(
        last_name='Рахимов', first_name='Тимур', patronymic='Рустамович',
        birth_date=date(1978, 11, 3), gender='M', snils='101-201-301 41',
        phone='+998 93 100-20-30', address='Ташкент, Яшнабад',
        notes=f'{DEMO_TAG} хроническая гипертензия',
        policies=[('OMS', 'AB000002', 'УВС ОМС', date(2024, 1, 1), date(2027, 12, 31))],
    ),
    dict(
        last_name='Каримова', first_name='Дилноза', patronymic='Курбановна',
        birth_date=date(2018, 7, 15), gender='F', snils='102-202-302 42',
        phone='+998 94 300-40-50', address='Ташкент, Мирзо-Улугбек',
        notes=f'{DEMO_TAG} ребёнок, плановый осмотр',
        policies=[('OMS', 'AB000003', 'УВС ОМС', date(2024, 1, 1), date(2027, 12, 31))],
    ),
    dict(
        last_name='Петров', first_name='Николай', patronymic='Иванович',
        birth_date=date(1952, 1, 9), gender='M', snils='103-203-303 43',
        phone='+998 91 700-80-90', address='Ташкент, Шайхантахур',
        notes=f'{DEMO_TAG} полис просрочен — проверка бейджа',
        policies=[('OMS', 'AB000004', 'УВС ОМС', date(2021, 1, 1), date(2025, 12, 31))],
    ),
    dict(
        last_name='Юсупова', first_name='Гульнара', patronymic='Абдуллаевна',
        birth_date=date(1965, 3, 28), gender='F', snils='104-204-304 44',
        phone='+998 97 111-33-55', address='Ташкент, Юнусабад',
        notes=f'{DEMO_TAG} ДМС от работодателя',
        policies=[('DMS', 'D777001', 'СК «Хаёт»', date(2026, 1, 1), date(2026, 12, 31))],
    ),
    dict(
        last_name='Назаров', first_name='Азиз', patronymic='Маратович',
        birth_date=date(1999, 12, 1), gender='M', snils='',
        phone='+998 92 444-55-66', address='Ташкент, Сергели',
        notes=f'{DEMO_TAG} без СНИЛС и полиса — проверка пустых полей',
        policies=[],
    ),
    dict(
        last_name='Фёдорова', first_name='Ольга', patronymic='Викторовна',
        birth_date=date(1988, 8, 18), gender='F', snils='105-205-305 45',
        phone='+998 90 606-07-08', address='Ташкент, Миробод',
        notes=f'{DEMO_TAG}',
        policies=[('OMS', 'AB000005', 'УВС ОМС', date(2024, 1, 1), date(2027, 12, 31))],
    ),
    dict(
        last_name='Тураев', first_name='Санжар', patronymic='Шухратович',
        birth_date=date(1972, 2, 14), gender='M', snils='106-206-306 46',
        phone='+998 91 909-10-11', address='Ташкент, Учтепа',
        notes=f'{DEMO_TAG} полис не оформлен',
        policies=[],
    ),
    dict(
        last_name='Мамедова', first_name='Зульфия', patronymic='Рамизовна',
        birth_date=date(1957, 6, 30), gender='F', snils='107-207-307 47',
        phone='+998 93 212-31-41', address='Ташкент, Шайхантахур',
        notes=f'{DEMO_TAG} ДМС истёк — проверка бейджа',
        policies=[('DMS', 'D777002', 'СК «Хаёт»', date(2025, 1, 1), date(2026, 3, 31))],
    ),
    dict(
        last_name='Ким', first_name='Алексей', patronymic='Валерьевич',
        birth_date=date(2003, 9, 5), gender='M', snils='108-208-308 48',
        phone='+998 94 515-61-71', address='Ташкент, Яккасарай',
        notes=f'{DEMO_TAG} студент',
        policies=[('OMS', 'AB000006', 'УВС ОМС', date(2024, 1, 1), date(2027, 12, 31))],
    ),
    dict(
        last_name='Алиева', first_name='Нигора', patronymic='Рустамовна',
        birth_date=date(1995, 4, 22), gender='F', snils='109-209-309 49',
        phone='+998 90 818-92-03', address='Ташкент, Чиланзар',
        notes=f'{DEMO_TAG} беременность, наблюдение',
        policies=[('OMS', 'AB000007', 'УВС ОМС', date(2024, 1, 1), date(2027, 12, 31))],
    ),
    dict(
        last_name='Волков', first_name='Дмитрий', patronymic='Сергеевич',
        birth_date=date(1981, 10, 7), gender='M', snils='110-210-310 50',
        phone='+998 97 343-54-64', address='Ташкент, Мирзо-Улугбек',
        notes=f'{DEMO_TAG}',
        policies=[],
    ),
    dict(
        last_name='Юлдашева', first_name='Малика', patronymic='Эркиновна',
        birth_date=date(2012, 12, 19), gender='F', snils='111-211-311 51',
        phone='+998 92 767-87-97', address='Ташкент, Сергели',
        notes=f'{DEMO_TAG} несовершеннолетняя — приём с сопровождением',
        policies=[('OMS', 'AB000008', 'УВС ОМС', date(2024, 1, 1), date(2027, 12, 31))],
    ),
    dict(
        last_name='Гусев', first_name='Павел', patronymic='Олегович',
        birth_date=date(1969, 7, 2), gender='M', snils='112-212-312 52',
        phone='+998 91 131-41-51', address='Ташкент, Юнусабад',
        notes=f'{DEMO_TAG}',
        policies=[('DMS', 'D777003', 'СК «Аллома»', date(2026, 1, 1), date(2026, 12, 31))],
    ),
    dict(
        last_name='Расулова', first_name='Замира', patronymic='Исмаиловна',
        birth_date=date(1954, 3, 11), gender='F', snils='113-213-313 53',
        phone='+998 93 656-76-86', address='Ташкент, Шайхантахур',
        notes=f'{DEMO_TAG} деактивирована — проверка скрытия из списка',
        policies=[('OMS', 'AB000009', 'УВС ОМС', date(2024, 1, 1), date(2027, 12, 31))],
        is_active=False,
    ),
]

# Справочники
DEMO_SPECIALTIES = [
    ('Терапевт', 'TER'), ('Педиатр', 'PED'), ('Кардиолог', 'KAR'),
    ('Невролог', 'NEV'), ('ЛОР', 'ENT'), ('Окулист', 'OFT'),
    # расширение пилота: больше специальностей
    ('Хирург', 'SUR'), ('Травматолог', 'TRA'), ('Уролог', 'URO'),
    ('Гинеколог', 'GYN'), ('Эндокринолог', 'END'), ('Дерматолог', 'DER'),
    ('Аллерголог', 'ALL'), ('Психиатр', 'PSY'),
    ('Гастроэнтеролог', 'GAST'),
]
DEMO_CABINETS = [
    ('101', 1, 'А'), ('102', 1, 'А'), ('103', 1, 'А'),
    ('104', 1, 'А'), ('105', 1, 'А'), ('106', 1, 'А'),
    # 203 намеренно остаётся без врача — «пустой кабинет» в справочнике
    ('201', 2, 'Б'), ('202', 2, 'Б'), ('203', 2, 'Б'),
    ('204', 2, 'Б'), ('205', 2, 'Б'), ('206', 2, 'Б'),
    ('301', 3, 'В'), ('302', 3, 'В'), ('303', 3, 'В'), ('304', 3, 'В'),
]

DEMO_DEPARTMENTS = [
    ('Терапевтическое отделение', 'ТО'),
    ('Кардиологическое отделение', 'КО'),
    ('Детское отделение', 'ДО'),
    ('Хирургическое отделение', 'ХО'),
    ('Гинекологическое отделение', 'ГО'),
    # расширение пилота: отделы под новые специальности
    ('Неврологическое отделение', 'НЕ'),
    ('ЛОР-отделение', 'ЛО'),
    ('Офтальмологическое отделение', 'ОФ'),
    ('Кожно-аллергологическое отделение', 'КА'),
    ('Психиатрическое отделение', 'ПС'),
    ('Гастроэнтерологическое отделение', 'ГЭ'),
]

# какому демо-врачу какой отдел
DEMO_DOCTOR_DEPARTMENT = {
    'doctor1': 'Терапевтическое отделение',
    'doctor2': 'Кардиологическое отделение',
    'doctor3': 'Детское отделение',
    'doctor4': 'Неврологическое отделение',
    'doctor5': 'ЛОР-отделение',
    'doctor6': 'Офтальмологическое отделение',
    'doctor7': 'Хирургическое отделение',
    'doctor8': 'Хирургическое отделение',
    'doctor9': 'Хирургическое отделение',
    'doctor10': 'Гинекологическое отделение',
    'doctor11': 'Терапевтическое отделение',
    'doctor12': 'Кожно-аллергологическое отделение',
    'doctor13': 'Кожно-аллергологическое отделение',
    'doctor14': 'Психиатрическое отделение',
    'doctor15': 'Гастроэнтерологическое отделение',
}

# какие специальности входят в отдел (для валидации связки)
DEMO_DEPARTMENT_SPECIALTIES = {
    'Терапевтическое отделение': ['Терапевт', 'Эндокринолог'],
    'Кардиологическое отделение': ['Кардиолог'],
    'Детское отделение': ['Педиатр'],
    'Хирургическое отделение': ['Хирург', 'Травматолог', 'Уролог'],
    'Гинекологическое отделение': ['Гинеколог'],
    'Неврологическое отделение': ['Невролог'],
    'ЛОР-отделение': ['ЛОР'],
    'Офтальмологическое отделение': ['Окулист'],
    'Кожно-аллергологическое отделение': ['Дерматолог', 'Аллерголог'],
    'Психиатрическое отделение': ['Психиатр'],
    'Гастроэнтерологическое отделение': ['Гастроэнтеролог'],
}

_MON_FRI = (1, 2, 3, 4, 5)

# Врачи и их недельное расписание:
# (username, специальность, кабинет, [(weekday, начало, конец, слот_мин), ...])
DEMO_DOCTORS = [
    ('doctor1', 'Терапевт', '101',
     [(wd, '09:00', '13:00', 20) for wd in _MON_FRI] +
     [(wd, '14:00', '17:00', 20) for wd in _MON_FRI]),
    ('doctor2', 'Кардиолог', '103',
     [(wd, '10:00', '14:00', 30) for wd in (1, 3, 5)]),
    ('doctor3', 'Педиатр', '102',
     [(2, '09:00', '12:00', 20), (4, '09:00', '12:00', 20), (6, '10:00', '13:00', 30)]),
    # расширение пилота: врач на каждую оставшуюся специальность
    ('doctor4', 'Невролог', '104',
     [(wd, '09:00', '13:00', 30) for wd in _MON_FRI]),
    ('doctor5', 'ЛОР', '105',
     [(wd, '13:00', '16:00', 20) for wd in (1, 3, 5)]),
    ('doctor6', 'Окулист', '106',
     [(2, '10:00', '13:00', 20), (4, '10:00', '13:00', 20)]),
    ('doctor7', 'Хирург', '201',
     [(wd, '08:00', '11:00', 30) for wd in _MON_FRI]),
    ('doctor8', 'Травматолог', '202',
     [(wd, '12:00', '15:00', 30) for wd in (1, 2, 4, 6)]),
    ('doctor9', 'Уролог', '204',
     [(wd, '14:00', '17:00', 30) for wd in (1, 3, 5)]),
    ('doctor10', 'Гинеколог', '205',
     [(2, '09:00', '12:00', 20), (4, '09:00', '12:00', 20)]),
    ('doctor11', 'Эндокринолог', '206',
     [(wd, '11:00', '14:00', 30) for wd in _MON_FRI]),
    ('doctor12', 'Дерматолог', '301',
     [(1, '15:00', '18:00', 20), (5, '15:00', '18:00', 20)]),
    ('doctor13', 'Аллерголог', '302',
     [(2, '14:00', '17:00', 30), (4, '14:00', '17:00', 30)]),
    ('doctor14', 'Психиатр', '303',
     [(wd, '16:00', '19:00', 30) for wd in _MON_FRI]),
    ('doctor15', 'Гастроэнтеролог', '304',
     [(wd, '12:00', '15:00', 30) for wd in _MON_FRI]),
]

DEMO_DOCTOR_USERNAMES = [d[0] for d in DEMO_DOCTORS]

# Направления в регистратуру (статус «новое» — видны регистратору):
# (фамилия пациента, специальность-цель, причина, кто направил-username)
DEMO_DIRECTIONS = [
    ('Рахимов', 'Кардиолог',
     f'{DEMO_TAG} направление терапевта: уточнить тактику лечения АГ',
     'doctor1'),
    ('Каримова', 'Педиатр',
     f'{DEMO_TAG} направление: плановый осмотр ребёнка',
     'doctor1'),
]

# заполненная карточка врача: стаж и био (маркер [demo]); фото не создаём —
# для карточки работает аватар по инициалам
DEMO_DOCTOR_INFO = {
    'doctor1': {
        'experience_years': 15,
        'bio': '[demo] Ведёт приём взрослых, занимается профилактикой и '
               'лечение хронических заболеваний. Ведёт пациентов в '
               'поликлинике с 2011 года.',
    },
    'doctor2': {
        'experience_years': 12,
        'bio': '[demo] Консультирует по вопросам сердечно-сосудистых '
               'заболеваний, ЭКГ-диагностика, наблюдение гипертоников.',
    },
    'doctor3': {
        'experience_years': 8,
        'bio': '[demo] Приём детей от рождения до 18 лет: плановая '
               'диспансеризация, вакцинация, лечение ОРВИ.',
    },
    'doctor4': {
        'experience_years': 11,
        'bio': '[demo] Головные боли, остеохондроз, невропатии; '
               'ведёт пациентов с хронической неврологической патологией.',
    },
    'doctor5': {
        'experience_years': 9,
        'bio': '[demo] ЛОР-заболевания взрослых и детей: тонзиллиты, '
               'риниты, снижение слуха, промывание миндалин.',
    },
    'doctor6': {
        'experience_years': 14,
        'bio': '[demo] Проверка зрения, подбор очков и линз, '
               'лечение конъюнктивитов, наблюдение глаукомы.',
    },
    'doctor7': {
        'experience_years': 17,
        'bio': '[demo] Плановая и экстренная хирургия: грыжи, '
               'острый аппендицит, новообразования мягких тканей.',
    },
    'doctor8': {
        'experience_years': 10,
        'bio': '[demo] Переломы, вывихи, растяжения, восстановление '
               'после травм опорно-двигательного аппарата.',
    },
    'doctor9': {
        'experience_years': 12,
        'bio': '[demo] Консультации по заболеваниям мочевыводящих путей, '
               'УЗД-диагностика, профилактические осмотры.',
    },
    'doctor10': {
        'experience_years': 13,
        'bio': '[demo] Ведение беременности, профилактические осмотры, '
               'лечение воспалительных заболеваний.',
    },
    'doctor11': {
        'experience_years': 7,
        'bio': '[demo] Сахарный диабет, болезни щитовидной железы, '
               'подбор терапии и контроль анализов.',
    },
    'doctor12': {
        'experience_years': 6,
        'bio': '[demo] Дерматиты, экзема, акне, грибковые и '
               'аллергические поражения кожи.',
    },
    'doctor13': {
        'experience_years': 8,
        'bio': '[demo] Поллинозы, пищевая и лекарственная аллергия, '
               'аллергопробы и иммунотерапия.',
    },
    'doctor14': {
        'experience_years': 16,
        'bio': '[demo] Тревожные и депрессивные состояния, бессонница; '
               'консультации в спокойной обстановке.',
    },
    'doctor15': {
        'experience_years': 15,
        'bio': '[demo] Заболевания желудка и кишечника, гастриты, '
               'язвенная болезнь, ФГДС-диагностика.',
    },
}


class Command(BaseCommand):
    help = 'Создаёт демо-данные: пользователи, пациенты, справочники, расписание, записи.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Удалить существующие демо-данные и создать заново',
        )

    def handle(self, *args, **options):
        reset = options['reset']

        # 1. Группы и права (идемпотентно)
        call_command('init_roles')

        # 2. Очистка демо-данных при --reset
        if reset:
            # направления ссылаются на пациентов (PROTECT) — удаляем первыми
            dirs, _ = Direction.objects.filter(
                reason__startswith=DEMO_TAG,
            ).delete()
            appts, _ = Appointment.objects.filter(
                Q(comment__startswith=DEMO_TAG) |
                Q(doctor__user__username__in=DEMO_DOCTOR_USERNAMES),
            ).delete()
            patients, _ = Patient.objects.filter(
                notes__startswith=DEMO_TAG,
            ).delete()
            users, _ = User.objects.filter(
                username__in=[u[0] for u in DEMO_USERS],
            ).delete()
            # справочники — только если на них больше никто не ссылается
            specs, _ = Specialty.objects.filter(
                name__in=[s[0] for s in DEMO_SPECIALTIES], doctors__isnull=True,
            ).delete()
            cabs, _ = Cabinet.objects.filter(
                number__in=[c[0] for c in DEMO_CABINETS], doctors__isnull=True,
            ).delete()
            deps, _ = Department.objects.filter(
                name__in=[d[0] for d in DEMO_DEPARTMENTS],
                doctors__isnull=True,
            ).delete()
            self.stdout.write(
                f'Удалено: направлений — {dirs}, записей — {appts}, '
                f'пациентов — {patients}, '
                f'пользователей — {users}, специальностей — {specs}, '
                f'кабинетов — {cabs}, отделов — {deps}'
            )

        # 3. Пользователи с ролями
        created_users = 0
        for username, password, role, full_name in DEMO_USERS:
            parts = full_name.split()
            # DEMO_USERS заданы как «Имя Фамилия»
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': parts[0],
                    'last_name': parts[1],
                    'is_staff': role == Roles.ADMINISTRATOR,
                },
            )
            user.set_password(password)  # пароли детерминированы для пилота
            user.save()
            user.groups.set(Group.objects.filter(name=role))
            created_users += int(created)

        # 4. Пациенты (идемпотентно, если не --reset)
        existing = Patient.objects.filter(notes__startswith=DEMO_TAG).exists()
        if existing and not reset:
            self.stdout.write(self.style.WARNING(
                'Демо-пациенты уже есть — пропускаю (используйте --reset для пересоздания).'
            ))
        else:
            created_patients = 0
            for data in DEMO_PATIENTS:
                policies = data.pop('policies', [])
                is_active = data.pop('is_active', True)
                patient = Patient.objects.create(is_active=is_active, **data)
                for p_type, number, insurer, valid_from, valid_to in policies:
                    InsurancePolicy.objects.create(
                        patient=patient, policy_type=p_type, number=number,
                        insurer=insurer, valid_from=valid_from, valid_to=valid_to,
                    )
                data['policies'] = policies
                data['is_active'] = is_active
                created_patients += 1
            self.stdout.write(self.style.SUCCESS(
                f'Создано демо-пациентов: {created_patients}'
            ))

        # 5. Справочники
        for name, code in DEMO_SPECIALTIES:
            Specialty.objects.get_or_create(name=name, defaults={'code': code})
        for number, floor, building in DEMO_CABINETS:
            Cabinet.objects.get_or_create(
                number=number,
                defaults={'floor': floor, 'building': building},
            )
        for name, code in DEMO_DEPARTMENTS:
            Department.objects.get_or_create(name=name, defaults={'code': code})
        # соответствие «отдел ⇄ специальность» (add — не затираем правки админа)
        for dep_name, spec_names in DEMO_DEPARTMENT_SPECIALTIES.items():
            Department.objects.get(name=dep_name).specialties.add(
                *Specialty.objects.filter(name__in=spec_names),
            )

        # 6. Врачи (профили поверх пользователей)
        for username, spec_name, cab_number, _slots in DEMO_DOCTORS:
            user = User.objects.get(username=username)
            specialty = Specialty.objects.get(name=spec_name)
            cabinet = Cabinet.objects.get(number=cab_number)
            department = Department.objects.get(
                name=DEMO_DOCTOR_DEPARTMENT[username],
            )
            doctor, _created = Doctor.objects.get_or_create(
                user=user,
                defaults={
                    'specialty': specialty, 'cabinet': cabinet,
                    'department': department, 'is_active': True,
                },
            )
            # врачи из прежних запусков без отдела — донашиваем
            if doctor.department_id is None:
                doctor.department = department
                doctor.save(update_fields=['department'])
            # карточка врача: стаж и био (идемпотентно, всегда к демо-значению)
            info = DEMO_DOCTOR_INFO.get(username)
            if info and (
                doctor.experience_years != info['experience_years']
                or doctor.bio != info['bio']
            ):
                doctor.experience_years = info['experience_years']
                doctor.bio = info['bio']
                doctor.save(update_fields=['experience_years', 'bio'])

        # 7. Расписание приёма
        schedules_created = 0
        for username, _spec, _cab, slots in DEMO_DOCTORS:
            doctor = Doctor.objects.get(user__username=username)
            for weekday, start, end, slot_min in slots:
                _s, created = WorkSchedule.objects.get_or_create(
                    doctor=doctor, weekday=weekday,
                    start_time=datetime.strptime(start, '%H:%M').time(),
                    defaults={
                        'end_time': datetime.strptime(end, '%H:%M').time(),
                        'slot_minutes': slot_min,
                    },
                )
                schedules_created += int(created)

        # 8. Записи на сегодня и завтра
        appts_created = self._seed_appointments(reset)

        # 9. История за прошлые 7 дней (для отчётов)
        history_created = self._seed_history(reset)

        # 10. Направления в регистратуру
        directions_created = self._seed_directions()

        total_patients = Patient.objects.filter(notes__startswith=DEMO_TAG).count()
        total_appts = Appointment.objects.filter(comment__startswith=DEMO_TAG).count()
        self.stdout.write(self.style.SUCCESS(
            f'Готово. Пациентов: {total_patients}, записей: {total_appts}; '
            f'за запуск: пользователей — {created_users}, '
            f'расписаний — {schedules_created}, записей — {appts_created}, '
            f'истории — {history_created}, направлений — {directions_created}.'
        ))

    def _seed_directions(self):
        """Направления в регистратуру (статус «новое») — идемпотентно."""
        if Direction.objects.filter(reason__startswith=DEMO_TAG).exists():
            self.stdout.write('Демо-направления уже есть — пропускаю.')
            return 0
        created = 0
        for patient_last, spec_name, reason, from_username in DEMO_DIRECTIONS:
            patient = Patient.objects.filter(
                notes__startswith=DEMO_TAG,
                last_name=patient_last, is_active=True,
            ).first()
            specialty = Specialty.objects.filter(name=spec_name).first()
            from_doctor = Doctor.objects.filter(
                user__username=from_username,
            ).select_related('user').first()
            if patient is None or specialty is None:
                continue
            Direction.objects.create(
                patient=patient,
                specialty=specialty,
                reason=reason,
                from_doctor=from_doctor,
                created_by=from_doctor.user if from_doctor else None,
            )
            created += 1
        self.stdout.write(self.style.SUCCESS(f'Создано демо-направлений: {created}'))
        return created

    def _seed_appointments(self, reset):
        """До 3 записей на сегодня и на завтра по свободным слотам демо-врачей."""
        if not reset and Appointment.objects.filter(
            comment__startswith=DEMO_TAG,
        ).exists():
            self.stdout.write('Демо-записи уже есть — пропускаю.')
            return 0

        demo_patients = list(
            Patient.objects.filter(notes__startswith=DEMO_TAG, is_active=True),
        )
        if not demo_patients:
            return 0
        registrar = User.objects.filter(username='registrar1').first()
        doctors = list(
            Doctor.objects.filter(
                user__username__in=DEMO_DOCTOR_USERNAMES,
            ).select_related('user', 'specialty'),
        )

        # История и «живая» очередь: сегодня — завершён/неявка/очередь,
        # завтра — подтверждён/забронирован/отменён.
        today = date.today()
        day1_statuses = [
            (Appointment.Status.DONE, '',
             '[demo] осмотр состоялся, жалоб нет'),
            (Appointment.Status.NO_SHOW, '', ''),
            (Appointment.Status.BOOKED, '', ''),
        ]
        day2_statuses = [
            (Appointment.Status.CONFIRMED, '', ''),
            (Appointment.Status.BOOKED, '', ''),
            (Appointment.Status.CANCELLED_REGISTRAR,
             'Демо: перенос по просьбе пациента', ''),
        ]
        status_sets = [
            (today, day1_statuses),
            (today + timedelta(days=1), day2_statuses),
        ]
        created = 0
        for day, statuses in status_sets:
            wanted = 3
            for doctor in doctors:
                if wanted == 0:
                    break
                free = [
                    s for s in generate_slots(doctor, day)
                    if not s['busy'] and not s['past']
                ]
                for slot in free:
                    if wanted == 0:
                        break
                    idx = created % len(statuses)
                    status, reason, note = statuses[idx]
                    Appointment.objects.create(
                        patient=demo_patients[created % len(demo_patients)],
                        doctor=doctor,
                        visit_date=day,
                        slot_start=slot['time'],
                        status=status,
                        cancel_reason=reason,
                        visit_note=note,
                        comment=f'{DEMO_TAG} демо-запись',
                        created_by=registrar,
                    )
                    created += 1
                    wanted -= 1
        self.stdout.write(self.style.SUCCESS(f'Создано демо-записей: {created}'))
        return created

    def _seed_history(self, reset):
        """
        История за 7 прошедших дней для отчётов: 2 записи в день
        в статусах done / no_show / cancelled (прошлые даты — только ORM,
        валидация «запись в прошлое» на записи не проверяется).
        """
        history_tag = f'{DEMO_TAG} история'
        if not reset and Appointment.objects.filter(
            comment__startswith=history_tag,
        ).exists():
            self.stdout.write('Демо-история уже есть — пропускаю.')
            return 0

        demo_patients = list(
            Patient.objects.filter(notes__startswith=DEMO_TAG, is_active=True),
        )
        if not demo_patients:
            return 0
        registrar = User.objects.filter(username='registrar1').first()
        doctors = list(
            Doctor.objects.filter(
                user__username__in=DEMO_DOCTOR_USERNAMES,
            ).select_related('user', 'specialty'),
        )

        statuses = [
            (Appointment.Status.DONE, '', '[demo] осмотр по истории'),
            (Appointment.Status.NO_SHOW, '', ''),
            (Appointment.Status.CANCELLED_REGISTRAR,
             'Демо: отмена накануне', ''),
        ]
        created = 0
        today = date.today()
        for offset in range(1, 8):  # 7 прошедших дней
            day = today - timedelta(days=offset)
            wanted = 2
            for doctor in doctors:
                if wanted == 0:
                    break
                free = [s for s in generate_slots(doctor, day)
                        if not s['busy']]  # прошлые слоты не «past»-фильтруем
                for slot in free:
                    if wanted == 0:
                        break
                    status, reason, note = statuses[created % len(statuses)]
                    Appointment.objects.create(
                        patient=demo_patients[created % len(demo_patients)],
                        doctor=doctor,
                        visit_date=day,
                        slot_start=slot['time'],
                        status=status,
                        cancel_reason=reason,
                        visit_note=note,
                        comment=history_tag,
                        created_by=registrar,
                    )
                    created += 1
                    wanted -= 1
        self.stdout.write(self.style.SUCCESS(f'Создано записей истории: {created}'))
        return created
