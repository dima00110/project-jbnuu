# Публичный код пациента (UUID) — для ссылки /p/<public_id>/ без входа.
#
# Три шага, потому что «добавить unique-поле с default=uuid4» одной командой
# Django заполнил бы ВСЕ существующие строки одним и тем же UUID и упал бы
# на UNIQUE constraint. Поэтому: сначала допускаем NULL, потом раздаём
# уникальные значения, потом включаем уникальность.

import uuid

from django.db import migrations, models


def assign_public_ids(apps, schema_editor):
    """Раздаёт каждому существующему пациенту собственный UUID."""
    Patient = apps.get_model('patients', 'Patient')
    for pk in Patient.objects.values_list('pk', flat=True):
        # update(), а не save() — модельные сигналы здесь не нужны
        Patient.objects.filter(pk=pk).update(public_id=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='public_id',
            field=models.UUIDField(
                db_index=True, null=True, editable=False,
                verbose_name='Публичный код',
            ),
        ),
        migrations.RunPython(
            assign_public_ids, migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='patient',
            name='public_id',
            field=models.UUIDField(
                db_index=True, default=uuid.uuid4, editable=False,
                unique=True, verbose_name='Публичный код',
            ),
        ),
    ]
