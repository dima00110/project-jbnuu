from django.core.exceptions import ValidationError
from django.db import models


class Specialty(models.Model):
    """Специальность врача (справочник)."""

    name = models.CharField('Название', max_length=100, unique=True)
    code = models.CharField('Код', max_length=20, blank=True)

    class Meta:
        verbose_name = 'Специальность'
        verbose_name_plural = 'Специальности'
        ordering = ['name']

    def __str__(self):
        return self.name


class Cabinet(models.Model):
    """Кабинет (справочник)."""

    number = models.CharField('Номер кабинета', max_length=16, unique=True)
    floor = models.PositiveSmallIntegerField('Этаж', default=1)
    building = models.CharField('Корпус', max_length=50, blank=True)

    class Meta:
        verbose_name = 'Кабинет'
        verbose_name_plural = 'Кабинеты'
        ordering = ['number']

    def __str__(self):
        extra = f', {self.building}' if self.building else ''
        return f'Кабинет {self.number} ({self.floor} этаж{extra})'


class Doctor(models.Model):
    """Врач — профиль поверх пользователя auth.User."""

    user = models.OneToOneField(
        'auth.User', on_delete=models.CASCADE,
        related_name='doctor_profile', verbose_name='Пользователь',
    )
    specialty = models.ForeignKey(
        Specialty, on_delete=models.PROTECT,
        related_name='doctors', verbose_name='Специальность',
    )
    cabinet = models.ForeignKey(
        Cabinet, on_delete=models.PROTECT,
        related_name='doctors', verbose_name='Кабинет',
        null=True, blank=True,
    )
    is_active = models.BooleanField('Активен', default=True)

    class Meta:
        verbose_name = 'Врач'
        verbose_name_plural = 'Врачи'
        ordering = ['user__last_name', 'user__first_name']

    def __str__(self):
        return f'{self.full_name} — {self.specialty}'

    @property
    def full_name(self):
        """Русский порядок: Фамилия Имя."""
        u = self.user
        if u.last_name or u.first_name:
            return ' '.join(p for p in (u.last_name, u.first_name) if p)
        return u.username


class WorkSchedule(models.Model):
    """Недельное расписание приёма врача."""

    WEEKDAYS = [
        (1, 'Понедельник'), (2, 'Вторник'), (3, 'Среда'),
        (4, 'Четверг'), (5, 'Пятница'), (6, 'Суббота'), (7, 'Воскресенье'),
    ]

    doctor = models.ForeignKey(
        Doctor, on_delete=models.CASCADE,
        related_name='schedules', verbose_name='Врач',
    )
    weekday = models.PositiveSmallIntegerField('День недели', choices=WEEKDAYS)
    start_time = models.TimeField('Начало приёма')
    end_time = models.TimeField('Конец приёма')
    slot_minutes = models.PositiveSmallIntegerField(
        'Длительность слота, мин', default=20,
    )
    valid_from = models.DateField(
        'Действует с', null=True, blank=True,
        help_text='Пусто — бессрочно',
    )
    valid_to = models.DateField(
        'Действует по', null=True, blank=True,
        help_text='Пусто — бессрочно',
    )

    class Meta:
        verbose_name = 'Расписание приёма'
        verbose_name_plural = 'Расписания приёма'
        ordering = ['doctor', 'weekday', 'start_time']
        unique_together = [('doctor', 'weekday', 'start_time')]

    def __str__(self):
        wd = self.get_weekday_display()[:2].upper()
        return (
            f'{self.full_doctor} {wd} {self.start_time:%H:%M}–{self.end_time:%H:%M} '
            f'(слот {self.slot_minutes} мин)'
        )

    @property
    def full_doctor(self):
        return str(self.doctor)

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({
                'end_time': 'Конец приёма должен быть позже начала.',
            })
        if self.slot_minutes and not (5 <= self.slot_minutes <= 120):
            raise ValidationError({
                'slot_minutes': 'Длительность слота: от 5 до 120 минут.',
            })
