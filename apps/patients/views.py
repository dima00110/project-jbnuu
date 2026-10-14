from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import Roles
from apps.appointments.models import Appointment, Direction
from apps.appointments.routing import find_candidates
from apps.queue.models import QueueTicket

from .forms import InsurancePolicyFormSet, PatientForm, PatientSearchForm
from .models import Patient


def _search_queryset(request):
    qs = Patient.objects.all()
    form = PatientSearchForm(request.GET or None)
    if form.is_valid():
        q = form.cleaned_data.get('q', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(last_name__icontains=q) |
                Q(first_name__icontains=q) |
                Q(patronymic__icontains=q) |
                Q(phone__icontains=q) |
                Q(snils__icontains=q)
            )
    return qs, form


@login_required
@role_required(Roles.REGISTRAR, Roles.ADMINISTRATOR, Roles.MANAGEMENT)
def patient_list(request):
    """Список пациентов с поиском (только активные)."""
    qs, form = _search_queryset(request)
    patients = [p for p in qs if p.is_active]
    return render(request, 'patients/patient_list.html', {
        'patients': patients,
        'search_form': form,
    })


@login_required
@role_required(Roles.REGISTRAR, Roles.ADMINISTRATOR)
def patient_create(request):
    """Регистрация нового пациента."""
    if request.method == 'POST':
        form = PatientForm(request.POST)
        formset = InsurancePolicyFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            patient = form.save()
            formset.instance = patient
            formset.save()
            messages.success(request, f'Пациент «{patient.full_name}» зарегистрирован.')
            return redirect('patients:patient_detail', pk=patient.pk)
    else:
        form = PatientForm()
        formset = InsurancePolicyFormSet()
    return render(request, 'patients/patient_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Новый пациент',
    })


@login_required
@role_required(Roles.REGISTRAR, Roles.ADMINISTRATOR, Roles.MANAGEMENT)
def patient_detail(request, pk):
    """Карточка пациента."""
    patient = get_object_or_404(
        Patient.objects.prefetch_related('policies'), pk=pk, is_active=True,
    )
    return render(request, 'patients/patient_detail.html', {
        'patient': patient,
        'policies': patient.policies.all(),
        'can_edit': request.user.is_superuser or request.user.groups.filter(
            name__in=[Roles.REGISTRAR, Roles.ADMINISTRATOR],
        ).exists(),
    })


@login_required
@role_required(Roles.REGISTRAR, Roles.ADMINISTRATOR)
def patient_edit(request, pk):
    """Редактирование карточки пациента и полисов."""
    patient = get_object_or_404(Patient, pk=pk, is_active=True)
    if request.method == 'POST':
        form = PatientForm(request.POST, instance=patient)
        formset = InsurancePolicyFormSet(request.POST, instance=patient)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Карточка «{patient.full_name}» обновлена.')
            return redirect('patients:patient_detail', pk=patient.pk)
    else:
        form = PatientForm(instance=patient)
        formset = InsurancePolicyFormSet(instance=patient)
    return render(request, 'patients/patient_form.html', {
        'form': form,
        'formset': formset,
        'title': f'Редактирование: {patient.full_name}',
        'patient': patient,
    })


@login_required
@role_required(Roles.REGISTRAR, Roles.ADMINISTRATOR)
def patient_deactivate(request, pk):
    """Мягкое удаление — карточка скрывается, история сохраняется."""
    patient = get_object_or_404(Patient, pk=pk, is_active=True)
    if request.method == 'POST':
        patient.is_active = False
        patient.save(update_fields=['is_active', 'updated_at'])
        messages.success(
            request,
            f'Карточка «{patient.full_name}» деактивирована (история сохранена).',
        )
        return redirect('patients:patient_list')
    return redirect('patients:patient_detail', pk=pk)


# --- Публичная страница пациента (без входа) -------------------------------


def patient_public(request, public_id):
    """
    Персональная страница пациента по секретной ссылке /p/<public_id>/.

    Доступна без аутентификации: пациент узнаёт UUID из талона/СМС.
    Показывает только данные самого пациента — ФИО, ближайшие и прошлые
    записи, номер в очереди сегодня. Неизвестный UUID → 404.
    """
    patient = get_object_or_404(
        Patient.objects.filter(is_active=True), public_id=public_id,
    )
    today = timezone.localdate()

    # Заявка с сайта (?new=<direction_pk>): баннер + подобранные врачи.
    # Направление обязано принадлежать этому пациенту — иначе игнорируем.
    new_direction = None
    candidates = []
    raw_new = request.GET.get('new')
    if raw_new and str(raw_new).isdigit():
        new_direction = Direction.objects.filter(
            pk=int(raw_new), patient=patient,
        ).select_related('specialty').first()
        if new_direction is not None:
            candidates = find_candidates(new_direction.specialty)

    upcoming = patient.appointments.filter(
        Q(visit_date__gte=today) & Q(status__in=Appointment.ACTIVE_STATUSES),
    ).select_related('doctor__user', 'doctor__specialty', 'doctor__cabinet')[:10]

    past = patient.appointments.filter(
        ~Q(status__in=Appointment.ACTIVE_STATUSES) | Q(visit_date__lt=today),
    ).select_related(
        'doctor__user', 'doctor__specialty', 'doctor__cabinet',
    ).order_by('-visit_date', '-slot_start')[:10]

    # Талон на сегодня (по записям пациента на сегодня)
    today_ticket = QueueTicket.objects.filter(
        appointment__patient=patient, visit_date=today,
    ).select_related('doctor__user', 'doctor__specialty').first()

    return render(request, 'patients/public.html', {
        'patient': patient,
        'upcoming': upcoming,
        'past': past,
        'today': today,
        'today_ticket': today_ticket,
        'new_direction': new_direction,
        'candidates': candidates,
        'card_created': request.GET.get('created') == '1',
    })
