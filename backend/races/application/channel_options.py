"""Opciones de lectura y de normalización de un canal, desde su configuración en la base de datos.

El dominio y los lectores no leen la base de datos: reciben estas opciones como parámetro.
"""

from __future__ import annotations

from dataclasses import dataclass

from races.domain.normalize import NormalizeOptions, alias_key
from races.infrastructure.sources import SourceOptions
from races.models import Channel, ValueAlias


class ChannelConfigError(Exception):
    """La configuración del canal no sirve. El mensaje es para el usuario."""


@dataclass(frozen=True)
class ChannelOptions:
    source: SourceOptions
    normalize: NormalizeOptions


def options_for(channel: Channel) -> ChannelOptions:
    """Columnas del canal y alias de valores: primero los globales y encima los del canal.

    Si un valor tiene alias global y alias del canal, manda el del canal. La comparación es la
    del normalizador (tras la limpieza común y sin distinguir mayúsculas), así que «2xl» del
    canal tapa a «2XL» global.
    """
    column_aliases = {column.source_header: column.field for column in channel.columns.all()}

    aliases: dict[str, dict[str, str]] = {}
    global_aliases = ValueAlias.objects.filter(channel__isnull=True)
    channel_aliases = ValueAlias.objects.filter(channel=channel)
    for queryset in (global_aliases, channel_aliases):
        for alias in queryset.order_by("id"):
            aliases.setdefault(alias.field, {})[alias_key(alias.source_value)] = alias.value

    try:
        normalize = NormalizeOptions(date_formats=channel.date_format_list, aliases=aliases)
    except ValueError as exc:
        raise ChannelConfigError(f"El canal «{channel.name}» está mal configurado: {exc}") from exc

    source = SourceOptions(
        format=channel.format,
        encoding=channel.encoding,
        delimiter=channel.delimiter,
        column_aliases=column_aliases,
    )
    return ChannelOptions(source=source, normalize=normalize)
