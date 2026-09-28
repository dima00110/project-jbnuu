"""Кастомные теги шаблонов для проверки ролей в навигации."""
from django import template

from apps.accounts.roles import has_role

register = template.Library()


@register.filter
def has_any_role(user, names):
    """{{ user|has_any_role:'administrator,management' }} — есть ли одна из ролей."""
    roles = [n.strip() for n in names.split(',') if n.strip()]
    return has_role(user, *roles)
