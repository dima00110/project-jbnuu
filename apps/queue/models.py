from django.db import models
from django.db.models import Max
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


def next_number(doctor, visit_date, exclude_pk=None):
    """Следующий номер талона для врача на дату."""
    qs = QueueTicket.objects.filter(doctor=doctor, visit_date=visit_date)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return (qs.aggregate(m=Max('number'))['m'] or 0) + 1


class QueueTicket(models.Model):
    """Электронный талон: номер в очереди врача на дату."""

    class Status(models.TextChoices):
        WAITING = 'waiting', 'В очереди'
        CALLED = 'called', 'Вызван'
        WITH_DOCTOR = 'with_doctor', 'У врача'
        COMPLETED = 'completed', 'Приём завершён'
        NO_SHOW = 'no_show', 'Неявка'
        CANCELLED = 'cancelled', 'Отменён'

    appointment = models.OneToOneField(
        'appointments.Appointment', on_delete=models.CASCADE,
        related_name='ticket', verbose_name='Запись',
    )
    number = models.PositiveIntegerField('Номер')
    visit_date = models.DateField('Дата визита', db_index=True)
    doctor = models.ForeignKey(
        'schedule.Doctor', on_delete=models.PROTECT,
        related_name='queue_tickets', verbose_name='Врач',
    )
    status = models.CharField(
        'Статус', max_length=16,
        choices=Status.choices, default=Status.WAITING,
    )
    called_at = models.DateTimeField('Вызван', null=True, blank=True)
    started_at = models.DateTimeField('У врача', null=True, blank=True)
    finished_at = models.DateTimeField('Завершён', null=True, blank=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)

    class Meta:
        verbose_name = 'Талон очереди'
        verbose_name_plural = 'Очередь'
        ordering = ['visit_date', 'doctor_id', 'number']
        constraints = [
            models.UniqueConstraint(
                fields=['visit_date', 'doctor', 'number'],
                name='unique_queue_number',
            ),
        ]

    def __str__(self):
        return f'№{self.number} {self.visit_date:%d.%m} — {self.doctor}'

    @property
    def is_open(self):
        return self.status in (
            self.Status.WAITING, self.Status.CALLED, self.Status.WITH_DOCTOR,
        )


@receiver(post_save, sender='appointments.Appointment')
def sync_ticket(sender, instance, **kwargs):
    """
    Синхронизация талона с записью:
    - активная запись → талон создаётся (при переносе — перенумеровывается);
    - done/no_show/отмена → талон закрывается соответствующим статусом.
    """
    from apps.appointments.models import Appointment

    appt = instance
    try:
        ticket = QueueTicket.objects.get(appointment=appt)
    except QueueTicket.DoesNotExist:
        ticket = None

    if ticket is None:
        # талон есть у каждой записи — история очереди полная
        ticket = QueueTicket.objects.create(
            appointment=appt,
            number=next_number(appt.doctor, appt.visit_date),
            visit_date=appt.visit_date,
            doctor=appt.doctor,
        )
    elif ticket.visit_date != appt.visit_date or \
            ticket.doctor_id != appt.doctor_id:
        # перенос записи — номер должен соответствовать новой дате/врачу
        ticket.visit_date = appt.visit_date
        ticket.doctor = appt.doctor
        ticket.number = next_number(
            appt.doctor, appt.visit_date, exclude_pk=ticket.pk,
        )
        ticket.save()

    if appt.status in Appointment.ACTIVE_STATUSES:
        return

    # неактивная запись → закрыть талон
    targets = {
        Appointment.Status.DONE: QueueTicket.Status.COMPLETED,
        Appointment.Status.NO_SHOW: QueueTicket.Status.NO_SHOW,
    }
    target = targets.get(appt.status, QueueTicket.Status.CANCELLED)
    if ticket.status in (QueueTicket.Status.WAITING,
                         QueueTicket.Status.CALLED,
                         QueueTicket.Status.WITH_DOCTOR):
        ticket.status = target
        ticket.finished_at = timezone.now()
        ticket.save()
