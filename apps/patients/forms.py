from django import forms

from .models import InsurancePolicy, Patient


class PatientForm(forms.ModelForm):
    """Форма карточки пациента."""

    class Meta:
        model = Patient
        fields = [
            'last_name', 'first_name', 'patronymic',
            'birth_date', 'gender', 'snils', 'phone',
            'email', 'address', 'notes',
        ]
        widgets = {
            'birth_date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'},
            ),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxInput):
                css = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = f'{css} form-control'.strip()
        self.fields['gender'].widget.attrs['class'] = 'form-select'
        self.fields['last_name'].required = True
        self.fields['first_name'].required = True

    def clean_phone(self):
        phone = (self.cleaned_data.get('phone') or '').strip()
        if phone:
            digits = ''.join(c for c in phone if c.isdigit())
            if len(digits) < 7:
                raise forms.ValidationError('Телефон слишком короткий.')
        return phone


class InsurancePolicyForm(forms.ModelForm):
    """Форма страхового полиса (в составе inline-формсета)."""

    class Meta:
        model = InsurancePolicy
        fields = ['policy_type', 'number', 'insurer', 'valid_from', 'valid_to']
        widgets = {
            'valid_from': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'valid_to': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{css} form-control'.strip()
        self.fields['policy_type'].widget.attrs['class'] = 'form-select'


InsurancePolicyFormSet = forms.inlineformset_factory(
    Patient, InsurancePolicy,
    form=InsurancePolicyForm,
    extra=1, can_delete=True,
)


class PatientSearchForm(forms.Form):
    """Поиск пациента по ФИО / телефону / СНИЛС."""

    q = forms.CharField(
        label='',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Поиск: ФИО, телефон или СНИЛС…',
            'autofocus': True,
        }),
    )
