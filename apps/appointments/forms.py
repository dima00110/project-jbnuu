from datetime import date as date_cls

from django import forms

from apps.patients.models import Patient
from apps.schedule.models import Doctor, Specialty

from .models import Appointment, Direction
from .slots import generate_slots


class AppointmentCreateForm(forms.ModelForm):
    """Запись на приём: валидирует доступность слота на сервере."""

    class Meta:
        model = Appointment
        fields = ['patient', 'doctor', 'visit_date', 'slot_start', 'visit_type', 'comment']
        widgets = {
            'patient': forms.HiddenInput,
            'doctor': forms.HiddenInput,
            'visit_date': forms.HiddenInput,
            'slot_start': forms.HiddenInput,
            'comment': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Комментарий (необязательно)',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['visit_type'].widget.attrs['class'] = 'form-select'

    def clean_visit_date(self):
        vd = self.cleaned_data['visit_date']
        if vd < date_cls.today():
            raise forms.ValidationError('Дата визита не может быть в прошлом.')
        return vd

    def clean(self):
        cleaned = super().clean()
        doctor = cleaned.get('doctor')
        visit_date = cleaned.get('visit_date')
        slot = cleaned.get('slot_start')
        patient = cleaned.get('patient')
        if not (doctor and visit_date and slot):
            return cleaned
        if not doctor.is_active:
            self.add_error('doctor', 'Врач недоступен для записи.')
        if patient and not patient.is_active:
            self.add_error('patient', 'Карточка пациента деактивирована.')
        slots = generate_slots(doctor, visit_date)
        match = next((s for s in slots if s['time'] == slot), None)
        if match is None:
            self.add_error('slot_start', 'Слот вне расписания врача.')
        elif match['past']:
            self.add_error('slot_start', 'Это время уже прошло.')
        elif match['busy']:
            self.add_error('slot_start', 'Слот уже занят.')
        return cleaned


class AppointmentMoveForm(forms.Form):
    """Перенос записи: валидирует новый слот, исключая саму запись."""

    visit_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    slot_start = forms.TimeField(
        widget=forms.HiddenInput,
    )
    appointment = None  # устанавливается во view

    def clean_visit_date(self):
        vd = self.cleaned_data['visit_date']
        if vd < date_cls.today():
            raise forms.ValidationError('Дата визита не может быть в прошлом.')
        return vd

    def clean(self):
        cleaned = super().clean()
        vd, slot = cleaned.get('visit_date'), cleaned.get('slot_start')
        appt = self.appointment
        if not (vd and slot and appt):
            return cleaned
        slots = generate_slots(appt.doctor, vd, exclude_pk=appt.pk)
        match = next((s for s in slots if s['time'] == slot), None)
        if match is None:
            self.add_error('slot_start', 'Слот вне расписания врача.')
        elif match['past']:
            self.add_error('slot_start', 'Это время уже прошло.')
        elif match['busy']:
            self.add_error('slot_start', 'Слот уже занят.')
        return cleaned


class AppointmentCancelForm(forms.Form):
    reason = forms.CharField(
        label='Причина отмены', max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Например: перенос по просьбе пациента',
        }),
    )


class DirectionCreateForm(forms.Form):
    """Направление: к какому специалисту направить и зачем."""

    specialty = forms.ModelChoiceField(
        label='Специальность (к кому направить)',
        queryset=Specialty.objects.all().order_by('name'),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    reason = forms.CharField(
        label='Причина направления', max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2,
            'placeholder': 'Например: консультация по результатам осмотра',
        }),
    )


class PatientRequestForm(forms.Form):
    """
    Публичная заявка нового пациента (/request/, без входа).

    Данные пациента + специальность → создаётся/находится карточка пациента
    и Direction в регистратуру, система подбирает свободных врачей.
    Уникальность СНИЛС здесь не проверяется — её заменяет дедупликация
    (apps.patients.services.find_or_create_patient).
    """

    last_name = forms.CharField(label='Фамилия', max_length=100)
    first_name = forms.CharField(label='Имя', max_length=100)
    patronymic = forms.CharField(
        label='Отчество', max_length=100, required=False,
    )
    birth_date = forms.DateField(
        label='Дата рождения',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    gender = forms.ChoiceField(
        label='Пол',
        choices=[('', '—')] + list(Patient.Gender.choices),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    snils = forms.CharField(
        label='СНИЛС', max_length=14, required=False,
        help_text='Опционально. Если есть в нашей базе — найдём вашу карточку.',
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'ХХХ-ХХХ-ХХХ ХХ',
        }),
    )
    phone = forms.CharField(
        label='Телефон', max_length=32,
        help_text='Позвоним, чтобы подтвердить запись.',
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': '+998 90 000-00-00',
        }),
    )
    email = forms.EmailField(
        label='Email', required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    specialty = forms.ModelChoiceField(
        label='К какому специалисту хотите записаться',
        queryset=Specialty.objects.filter(
            doctors__is_active=True,
        ).distinct().order_by('name'),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    reason = forms.CharField(
        label='Жалоба / причина обращения', max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 3,
            'placeholder': 'Например: головная боль, плановый осмотр…',
        }),
    )
    # honeypot: человек это поле не заполняет, бот — заполняет
    website = forms.CharField(
        required=False, widget=forms.HiddenInput(attrs={'autocomplete': 'off'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['last_name'].widget.attrs['class'] = 'form-control'
        self.fields['first_name'].widget.attrs['class'] = 'form-control'
        self.fields['patronymic'].widget.attrs['class'] = 'form-control'

    def clean_birth_date(self):
        bd = self.cleaned_data['birth_date']
        if bd > date_cls.today():
            raise forms.ValidationError('Дата рождения не может быть в будущем.')
        return bd

    def clean_gender(self):
        gender = self.cleaned_data.get('gender')
        if gender not in ('M', 'F'):
            raise forms.ValidationError('Выберите пол.')
        return gender

    def clean_phone(self):
        phone = (self.cleaned_data.get('phone') or '').strip()
        digits = ''.join(c for c in phone if c.isdigit())
        if len(digits) < 7:
            raise forms.ValidationError('Телефон слишком короткий.')
        return phone

    def clean_snils(self):
        snils = (self.cleaned_data.get('snils') or '').strip()
        if not snils:
            return snils
        digits = ''.join(c for c in snils if c.isdigit())
        if len(digits) != 11:
            raise forms.ValidationError(
                'СНИЛС должен содержать 11 цифр (формат ХХХ-ХХХ-ХХХ ХХ).',
            )
        return snils


class PatientQuickFindForm(forms.Form):
    """Быстрый выбор пациента для записи (поиск по списку)."""

    patient = forms.ModelChoiceField(
        label='Пациент',
        queryset=Patient.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class DoctorFilterForm(forms.Form):
    """Фильтр расписания/записей по дате и врачу."""

    date = forms.DateField(
        label='Дата',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    doctor = forms.ModelChoiceField(
        label='Врач', required=False,
        queryset=Doctor.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
