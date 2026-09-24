from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission

from apps.accounts.roles import Roles


# Коды permissions по приложениям
PATIENT_PERMS = {
    'add_patient', 'change_patient', 'view_patient', 'delete_patient',
}
POLICY_PERMS = {
    'add_insurancepolicy', 'change_insurancepolicy',
    'view_insurancepolicy', 'delete_insurancepolicy',
}
APPOINTMENT_PERMS = {
    'add_appointment', 'change_appointment', 'view_appointment',
}
SCHEDULE_PERMS = {
    'add_specialty', 'change_specialty', 'view_specialty', 'delete_specialty',
    'add_cabinet', 'change_cabinet', 'view_cabinet', 'delete_cabinet',
    'add_doctor', 'change_doctor', 'view_doctor',
    'add_workschedule', 'change_workschedule', 'view_workschedule',
    'delete_workschedule',
}
QUEUE_PERMS = {
    'add_queueticket', 'change_queueticket',
    'view_queueticket', 'delete_queueticket',
}

ALL_CODES = PATIENT_PERMS | POLICY_PERMS | APPOINTMENT_PERMS | SCHEDULE_PERMS | QUEUE_PERMS


class Command(BaseCommand):
    help = 'Синхронизирует группы ролей с актуальным набором прав.'

    def handle(self, *args, **options):
        grants = {
            Roles.REGISTRAR: (
                PATIENT_PERMS | POLICY_PERMS | APPOINTMENT_PERMS | QUEUE_PERMS
            ),
            Roles.ADMINISTRATOR: (
                PATIENT_PERMS | POLICY_PERMS | APPOINTMENT_PERMS
                | SCHEDULE_PERMS | QUEUE_PERMS
            ),
            Roles.DOCTOR: {
                'change_appointment',
                'view_queueticket', 'change_queueticket',
            },
            Roles.MANAGEMENT: {
                'view_patient', 'view_insurancepolicy',
                'view_appointment', 'view_specialty',
                'view_cabinet', 'view_doctor', 'view_workschedule',
                'view_queueticket',
            },
        }

        all_perms = Permission.objects.filter(codename__in=ALL_CODES)
        known = {p.codename for p in all_perms}

        for role, codenames in grants.items():
            group, created = Group.objects.get_or_create(name=role)
            group.permissions.remove(*all_perms)
            granted = [p for p in all_perms if p.codename in codenames]
            unknown = codenames - known
            group.permissions.add(*granted)
            state = 'создана' if created else 'обновлена'
            line = f'Группа «{role}» {state}, прав: {len(granted)}'
            if unknown:
                line += f' (не найдено: {", ".join(sorted(unknown))})'
            self.stdout.write(self.style.SUCCESS(line))

        self.stdout.write(self.style.SUCCESS('Роли готовы.'))
