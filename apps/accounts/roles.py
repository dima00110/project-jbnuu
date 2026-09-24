"""Константы ролей (Django Group) и вспомогательные функции."""


class Roles:
    """Имена групп ролей. Должны совпадать с accounts.management.commands.init_roles."""

    REGISTRAR = 'registrar'
    ADMINISTRATOR = 'administrator'
    DOCTOR = 'doctor'
    MANAGEMENT = 'management'

    ALL = (REGISTRAR, ADMINISTRATOR, DOCTOR, MANAGEMENT)

    LABELS = {
        REGISTRAR: 'Регистратор',
        ADMINISTRATOR: 'Администратор',
        DOCTOR: 'Врач',
        MANAGEMENT: 'Руководство',
    }


def user_roles(user):
    """Возвращает список названий ролей пользователя."""
    if not user.is_authenticated:
        return []
    if user.is_superuser:
        return ['Суперпользователь']
    return [
        Roles.LABELS.get(name, name)
        for name in user.groups.values_list('name', flat=True)
    ]


def has_role(user, *roles):
    """Проверка: есть ли у пользователя хотя бы одна из указанных ролей."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=roles).exists()
