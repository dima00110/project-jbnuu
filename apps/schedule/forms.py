from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from .models import Cabinet, Department, Doctor, Specialty, WorkSchedule


def _apply_bootstrap(form):
    for name, field in form.fields.items():
        css = field.widget.attrs.get('class', '')
        if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
            field.widget.attrs['class'] = f'{css} form-select'.strip()
        elif not isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect)):
            field.widget.attrs['class'] = f'{css} form-control'.strip()


class SpecialtyForm(forms.ModelForm):
    class Meta:
        model = Specialty
        fields = ['name', 'code']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)


class CabinetForm(forms.ModelForm):
    class Meta:
        model = Cabinet
        fields = ['number', 'floor', 'building']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code', 'specialties']
        widgets = {
            'specialties': forms.SelectMultiple(
                attrs={'size': '6', 'class': 'form-select'},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)


class DoctorForm(forms.ModelForm):
    """Создание врача: либо выбор существующего пользователя, либо новый логин."""

    existing_user = forms.ModelChoiceField(
        label='Существующий пользователь', required=False,
        queryset=User.objects.filter(doctor_profile__isnull=True, is_active=True),
        help_text='Оставить пустым, чтобы создать нового пользователя',
    )
    username = forms.CharField(
        label='Логин (новый пользователь)', required=False,
    )
    password = forms.CharField(
        label='Пароль', required=False, widget=forms.PasswordInput,
    )
    first_name = forms.CharField(label='Имя', required=False)
    last_name = forms.CharField(label='Фамилия', required=False)

    class Meta:
        model = Doctor
        fields = ['specialty', 'department', 'cabinet', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # при редактировании не предлагаем «висячих» пользователей
        qs = self.fields['existing_user'].queryset
        if self.instance.pk:
            qs = qs | User.objects.filter(pk=self.instance.user_id)
        self.fields['existing_user'].queryset = qs
        _apply_bootstrap(self)

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk:
            return cleaned  # редактирование: пользователь уже назначен
        user = cleaned.get('existing_user')
        username = (cleaned.get('username') or '').strip()
        password = cleaned.get('password') or ''
        if not user and not username:
            self.add_error(
                'username',
                'Укажите существующего пользователя или новый логин.',
            )
        if username:
            if User.objects.filter(username=username).exists():
                self.add_error('username', 'Пользователь с таким логином уже есть.')
            if not password:
                self.add_error('password', 'Пароль обязателен для нового пользователя.')
            else:
                validate_password(password)
            if not cleaned.get('first_name') or not cleaned.get('last_name'):
                self.add_error('first_name', 'Укажите имя и фамилию врача.')
        return cleaned


class WorkScheduleForm(forms.ModelForm):
    class Meta:
        model = WorkSchedule
        fields = [
            'doctor', 'weekday', 'start_time', 'end_time',
            'slot_minutes', 'valid_from', 'valid_to',
        ]
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'valid_from': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'valid_to': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self)
        self.fields['doctor'].queryset = Doctor.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('start_time'), cleaned.get('end_time')
        if start and end and start >= end:
            self.add_error('end_time', 'Конец приёма должен быть позже начала.')
        v_from, v_to = cleaned.get('valid_from'), cleaned.get('valid_to')
        if v_from and v_to and v_from > v_to:
            self.add_error('valid_to', 'Дата окончания раньше даты начала.')
        return cleaned
