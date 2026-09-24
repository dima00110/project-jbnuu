from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission

from apps.accounts.roles import Roles


# Коды permissions моделей пациентов (этап 1)
PATIENT_PERMS = {
    'add_patient',
    'change_patient',
    'view_patient',
    'delete_patient',
}
POLICY_PERMS = {
    'add_insurancepolicy',
    'change_insurancepolicy',
    'view_insurancepolicy',
    'delete_insurancepolicy',
}


class Command(BaseCommand):
    help = 'Создаёт группы ролей (регистратор, администратор, врач, руководство) и назначает права.'

    def handle(self, *args, **options):
        grants = {
            Roles.REGISTRAR: PATIENT_PERMS | POLICY_PERMS,
            Roles.ADMINISTRATOR: PATIENT_PERMS | POLICY_PERMS,
            Roles.DOCTOR: set(),            # этап 1: права врачей добавим с кабинетом врача
            Roles.MANAGEMENT: {'view_patient', 'view_insurancepolicy'},
        }

        all_perms = Permission.objects.filter(
            codename__in=PATIENT_PERMS | POLICY_PERMS,
        )

        for role, codenames in grants.items():
            group, created = Group.objects.get_or_create(name=role)
            # Синхронизируем права: сначала снимаем все «наши», затем вешаем нужные
            group.permissions.remove(*all_perms)
            granted = [p for p in all_perms if p.codename in codenames]
            group.permissions.add(*granted)
            state = 'создана' if created else 'обновлена'
            self.stdout.write(self.style.SUCCESS(
                f'Группа «{role}» {state}, прав: {len(granted)}'
            ))

        self.stdout.write(self.style.SUCCESS('Роли готовы.'))
