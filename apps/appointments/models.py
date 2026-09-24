from django.db import models
from django.db.models import Q


class Appointment(models.Model):
    """Запись пациента к врачу на конкретный слот времени."""

    class Status(models.TextChoices):
        BOOKED = 'booked', 'Записан'
        CONFIRMED = 'confirmed', 'Подтверждён'
        CANCELLED_PATIENT = 'cancelled_patient', 'Отменён пациентом'
        CANCELLED_REGISTRAR = 'cancelled_registrar', 'Отменён регистратором'
        NO_SHOW = 'no_show', 'Неявка'
        DONE = 'done', 'Завершён'

    class VisitType(models.TextChoices):
        PRIMARY = 'primary', 'Первичный'
        REPEAT = 'repeat', 'Повторный'

    # Статусы, занимающие слот
    ACTIVE_STATUSES = ('booked', 'confirmed')

    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.CASCADE,
        related_name='appointments', verbose_name='Пациент',
    )
    doctor = models.ForeignKey(
        'schedule.Doctor', on_delete=models.PROTECT,
        related_name='appointments', verbose_name='Врач',
    )
    visit_date = models.DateField('Дата визита', db_index=True)
    slot_start = models.TimeField('Время начала')
    visit_type = models.CharField(
        'Тип визита', max_length=10,
        choices=VisitType.choices, default=VisitType.PRIMARY,
    )
    status = models.CharField(
        'Статус', max_length=24,
        choices=Status.choices, default=Status.BOOKED,
    )
    cancel_reason = models.CharField('Причина отмены', max_length=200, blank=True)
    comment = models.CharField('Комментарий', max_length=200, blank=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, verbose_name='Кто записал',
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Изменено', auto_now=True)

    class Meta:
        verbose_name = 'Запись на приём'
        verbose_name_plural = 'Записи на приём'
        ordering = ['visit_date', 'slot_start']
        constraints = [
            models.UniqueConstraint(
                fields=['doctor', 'visit_date', 'slot_start'],
                condition=Q(status__in=('booked', 'confirmed')),
                name='unique_active_slot',
            ),
        ]

    def __str__(self):
        return (
            f'{self.patient} → {self.doctor} '
            f'{self.visit_date:%d.%m.%Y} {self.slot_start:%H:%M}'
        )

    @property
    def is_active(self):
        return self.status in self.ACTIVE_STATUSES
