from datetime import date as date_cls

from django import forms

from apps.patients.models import Patient
from apps.schedule.models import Doctor

from .models import Appointment
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
