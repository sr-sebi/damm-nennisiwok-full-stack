from django.db import migrations

# Los tres canales del cliente (docs/reglas-de-negocio.md). Codificación y separador vacíos: se
# detectan, así que la tienda (cp1252 y «;») funciona sin fijarlos.
CHANNELS = [
    {"code": "plataforma_a", "name": "Plataforma A", "kind": "plataforma_online", "format": "xlsx"},
    {"code": "plataforma_b", "name": "Plataforma B", "kind": "plataforma_online", "format": "csv"},
    {"code": "tienda", "name": "Tienda", "kind": "presencial", "format": "csv"},
]


def create_channels(apps, schema_editor):
    Channel = apps.get_model("races", "Channel")
    for data in CHANNELS:
        Channel.objects.get_or_create(code=data["code"], defaults=data)


def delete_channels(apps, schema_editor):
    Channel = apps.get_model("races", "Channel")
    Channel.objects.filter(code__in=[data["code"] for data in CHANNELS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("races", "0002_inscriptions"),
    ]

    operations = [
        migrations.RunPython(create_channels, delete_channels),
    ]
