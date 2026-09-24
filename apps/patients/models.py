from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Patient(models.Model):
    """Карточка пациента."""

    class Gender(models.TextChoices):
        MALE = 'M', 'Мужской'
        FEMALE = 'F', 'Женский'

    last_name = models.CharField('Фамилия', max_length=100)
    first_name = models.CharField('Имя', max_length=100)
    patronymic = models.CharField('Отчество', max_length=100, blank=True)
    birth_date = models.DateField('Дата рождения')
    gender = models.CharField('Пол', max_length=1, choices=Gender.choices)
    snils = models.CharField(
        'СНИЛС', max_length=14, blank=True,
        help_text='11 цифр, формат ХХХ-ХХХ-ХХХ XX (опционально)',
    )
    phone = models.CharField('Телефон', max_length=32, blank=True)
    email = models.EmailField('Email', blank=True)
    address = models.CharField('Адрес регистрации', max_length=255, blank=True)
    notes = models.TextField('Примечания', blank=True)
    is_active = models.BooleanField('Активен', default=True, db_index=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Изменено', auto_now=True)

    class Meta:
        verbose_name = 'Пациент'
        verbose_name_plural = 'Пациенты'
        ordering = ['last_name', 'first_name', 'patronymic']
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['phone']),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.patronymic]
        return ' '.join(p for p in parts if p)

    @property
    def age(self):
        """Возраст на текущую дату."""
        today = timezone.localdate()
        born = self.birth_date
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

    def clean(self):
        super().clean()
        if self.birth_date and self.birth_date > timezone.localdate():
            raise ValidationError({'birth_date': 'Дата рождения не может быть в будущем.'})
        if self.snils:
            digits = ''.join(c for c in self.snils if c.isdigit())
            if len(digits) != 11:
                raise ValidationError({'snils': 'СНИЛС должен содержать 11 цифр.'})
            dup = (
                Patient.objects.filter(snils=self.snils)
                .exclude(pk=self.pk).exists()
            )
            if dup:
                raise ValidationError({'snils': 'Пациент с таким СНИЛС уже существует.'})


class InsurancePolicy(models.Model):
    """Страховой полис пациента (ОМС/ДМС)."""

    class PolicyType(models.TextChoices):
        OMS = 'OMS', 'ОМС'
        DMS = 'DMS', 'ДМС'

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE,
        related_name='policies', verbose_name='Пациент',
    )
    policy_type = models.CharField('Тип полиса', max_length=3, choices=PolicyType.choices)
    number = models.CharField('Номер полиса', max_length=32)
    insurer = models.CharField('Страхователь', max_length=150, blank=True)
    valid_from = models.DateField('Действителен с', null=True, blank=True)
    valid_to = models.DateField('Действителен по', null=True, blank=True)

    class Meta:
        verbose_name = 'Страховой полис'
        verbose_name_plural = 'Страховые полисы'
        ordering = ['patient', 'policy_type']

    def __str__(self):
        return f'{self.get_policy_type_display()} №{self.number}'

    @property
    def is_valid(self):
        """Действителен ли полис на сегодняшнюю дату."""
        today = timezone.localdate()
        if self.valid_from and today < self.valid_from:
            return False
        if self.valid_to and today > self.valid_to:
            return False
        return True
