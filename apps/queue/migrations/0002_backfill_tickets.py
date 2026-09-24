from django.db import migrations


def create_tickets(apps, schema_editor):
    """Создаёт талоны для существующих активных записей."""
    Appointment = apps.get_model('appointments', 'Appointment')
    QueueTicket = apps.get_model('queue', 'QueueTicket')

    active = Appointment.objects.filter(
        status__in=('booked', 'confirmed'),
    ).order_by('visit_date', 'slot_start')

    counters = {}  # (doctor_id, visit_date) -> последний номер
    for appt in active.iterator():
        key = (appt.doctor_id, appt.visit_date)
        counters[key] = counters.get(key, 0) + 1
        QueueTicket.objects.create(
            appointment=appt,
            number=counters[key],
            visit_date=appt.visit_date,
            doctor_id=appt.doctor_id,
        )


def remove_tickets(apps, schema_editor):
    QueueTicket = apps.get_model('queue', 'QueueTicket')
    QueueTicket.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('queue', '0001_initial'),
        ('appointments', '0002_appointment_visit_note'),
    ]

    operations = [
        migrations.RunPython(create_tickets, remove_tickets),
    ]
