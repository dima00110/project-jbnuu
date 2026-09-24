from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .roles import Roles


def role_required(*roles):
    """
    Доступ только для указанных ролей (см. accounts.roles.Roles).

    Суперпользователь всегда проходит. Иначе — сообщение об ошибке
    и редирект на дашборд. Возвращает обёртку с @login_required,
    поэтому порядок декораторов на представлении не важен.
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if request.user.is_superuser or \
                    request.user.groups.filter(name__in=roles).exists():
                return view_func(request, *args, **kwargs)
            messages.error(
                request,
                'Недостаточно прав для доступа к разделу. '
                f'Требуется роль: {", ".join(Roles.LABELS.get(r, r) for r in roles)}.',
            )
            return redirect('dashboard')

        return _wrapped

    return decorator
