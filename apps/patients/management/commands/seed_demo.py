"""
Демо-данные для пилота: пользователи с ролями + пациенты с полисами.

Использование:
    python manage.py seed_demo            # добавить недостающие демо-данные
    python manage.py seed_demo --reset    # удалить демо-данные и создать заново

Пациенты помечены префиксом '[demo]' в поле notes — удаляются только они.
Пароли демо-пользователей при каждом запуске выставляются заново.
"""
from datetime import date

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.accounts.roles import Roles

from ...models import InsurancePolicy, Patient

DEMO_TAG = '[demo]'

# (username, password, role, full_name)
DEMO_USERS = [
    ('registrar1', 'registrar12345', Roles.REGISTRAR, 'Ирина Смирнова'),
    ('registrar2', 'registrar12345', Roles.REGISTRAR, 'Алексей Ковалёв'),
    ('doctor1', 'doctor12345', Roles.DOCTOR, 'Дмитрий Орлов'),
    ('manager', 'manager12345', Roles.MANAGEMENT, 'Главный сотрудник'),
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


class Command(BaseCommand):
    help = 'Создаёт демо-данные: пользователей с ролями и пациентов с полисами.'

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
            deleted_patients, _ = Patient.objects.filter(
                notes__startswith=DEMO_TAG,
            ).delete()
            deleted_users, _ = User.objects.filter(
                username__in=[u[0] for u in DEMO_USERS],
            ).delete()
            self.stdout.write(
                f'Удалено: пациентов — {deleted_patients}, пользователей — {deleted_users}'
            )

        # 3. Пользователи с ролями
        created_users = 0
        for username, password, role, full_name in DEMO_USERS:
            parts = full_name.split()
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': parts[1],
                    'last_name': parts[0],
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

        total = Patient.objects.filter(notes__startswith=DEMO_TAG).count()
        self.stdout.write(self.style.SUCCESS(
            f'Готово. Демо-пациентов в БД: {total}, '
            f'создано пользователей: {created_users}.'
        ))
