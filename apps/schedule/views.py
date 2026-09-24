from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import role_required
from apps.accounts.roles import Roles


from .forms import CabinetForm, DoctorForm, SpecialtyForm, WorkScheduleForm
from .models import Cabinet, Doctor, Specialty, WorkSchedule


# --- Специальности -------------------------------------------------------


@login_required
@role_required(Roles.ADMINISTRATOR, Roles.MANAGEMENT)
def specialty_list(request):
    items = Specialty.objects.all()
    return render(request, 'schedule/specialty_list.html', {'items': items})


@login_required
@role_required(Roles.ADMINISTRATOR)
def specialty_create(request):
    if request.method == 'POST':
        form = SpecialtyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Специальность добавлена.')
            return redirect('schedule:specialty_list')
    else:
        form = SpecialtyForm()
    return render(request, 'schedule/form.html', {
        'form': form, 'title': 'Новая специальность',
        'back_url': 'schedule:specialty_list',
    })


@login_required
@role_required(Roles.ADMINISTRATOR)
def specialty_edit(request, pk):
    item = get_object_or_404(Specialty, pk=pk)
    if request.method == 'POST':
        form = SpecialtyForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Специальность обновлена.')
            return redirect('schedule:specialty_list')
    else:
        form = SpecialtyForm(instance=item)
    return render(request, 'schedule/form.html', {
        'form': form, 'title': f'Специальность: {item}',
        'back_url': 'schedule:specialty_list',
    })


# --- Кабинеты -------------------------------------------------------------


@login_required
@role_required(Roles.ADMINISTRATOR, Roles.MANAGEMENT)
def cabinet_list(request):
    items = Cabinet.objects.all()
    return render(request, 'schedule/cabinet_list.html', {'items': items})


@login_required
@role_required(Roles.ADMINISTRATOR)
def cabinet_create(request):
    if request.method == 'POST':
        form = CabinetForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Кабинет добавлен.')
            return redirect('schedule:cabinet_list')
    else:
        form = CabinetForm()
    return render(request, 'schedule/form.html', {
        'form': form, 'title': 'Новый кабинет',
        'back_url': 'schedule:cabinet_list',
    })


@login_required
@role_required(Roles.ADMINISTRATOR)
def cabinet_edit(request, pk):
    item = get_object_or_404(Cabinet, pk=pk)
    if request.method == 'POST':
        form = CabinetForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Кабинет обновлён.')
            return redirect('schedule:cabinet_list')
    else:
        form = CabinetForm(instance=item)
    return render(request, 'schedule/form.html', {
        'form': form, 'title': f'Кабинет: {item}',
        'back_url': 'schedule:cabinet_list',
    })


# --- Врачи ----------------------------------------------------------------


@login_required
@role_required(Roles.ADMINISTRATOR, Roles.MANAGEMENT)
def doctor_list(request):
    items = Doctor.objects.select_related('user', 'specialty', 'cabinet')
    return render(request, 'schedule/doctor_list.html', {'items': items})


@login_required
@role_required(Roles.ADMINISTRATOR)
def doctor_create(request):
    if request.method == 'POST':
        form = DoctorForm(request.POST)
        if form.is_valid():
            doctor = form.save(commit=False)
            user = form.cleaned_data.get('existing_user')
            if not user:
                from django.contrib.auth.models import User
                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    password=form.cleaned_data['password'],
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                )
            doctor.user = user
            doctor.save()
            # новый пользователь-врач сразу получает роль doctor
            doctor_group, _ = Group.objects.get_or_create(name=Roles.DOCTOR)
            user.groups.add(doctor_group)
            messages.success(request, f'Врач «{doctor.full_name}» добавлен.')
            return redirect('schedule:doctor_list')
    else:
        form = DoctorForm()
    return render(request, 'schedule/form.html', {
        'form': form, 'title': 'Новый врач',
        'back_url': 'schedule:doctor_list',
    })


@login_required
@role_required(Roles.ADMINISTRATOR)
def doctor_edit(request, pk):
    item = get_object_or_404(Doctor, pk=pk)
    if request.method == 'POST':
        form = DoctorForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Данные врача обновлены.')
            return redirect('schedule:doctor_list')
    else:
        form = DoctorForm(instance=item)
    return render(request, 'schedule/form.html', {
        'form': form, 'title': f'Врач: {item.full_name}',
        'back_url': 'schedule:doctor_list',
    })


# --- Расписание -----------------------------------------------------------


@login_required
@role_required(Roles.ADMINISTRATOR, Roles.MANAGEMENT)
def workschedule_list(request):
    items = WorkSchedule.objects.select_related(
        'doctor__user', 'doctor__specialty',
    )
    return render(request, 'schedule/workschedule_list.html', {'items': items})


@login_required
@role_required(Roles.ADMINISTRATOR)
def workschedule_create(request):
    if request.method == 'POST':
        form = WorkScheduleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Расписание добавлено.')
            return redirect('schedule:workschedule_list')
    else:
        form = WorkScheduleForm()
    return render(request, 'schedule/form.html', {
        'form': form, 'title': 'Новое расписание',
        'back_url': 'schedule:workschedule_list',
    })


@login_required
@role_required(Roles.ADMINISTRATOR)
def workschedule_edit(request, pk):
    item = get_object_or_404(WorkSchedule, pk=pk)
    if request.method == 'POST':
        form = WorkScheduleForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Расписание обновлено.')
            return redirect('schedule:workschedule_list')
    else:
        form = WorkScheduleForm(instance=item)
    return render(request, 'schedule/form.html', {
        'form': form, 'title': f'Расписание: {item}',
        'back_url': 'schedule:workschedule_list',
    })


# --- Хаб справочников -----------------------------------------------------


@login_required
@role_required(Roles.ADMINISTRATOR, Roles.MANAGEMENT)
def hub(request):
    return render(request, 'schedule/hub.html')
