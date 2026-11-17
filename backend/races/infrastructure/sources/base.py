"""Tipos comunes de los lectores de formato."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Protocol

from races.domain.issues import Issue


class SourceError(Exception):
    """El fichero entero no se puede leer.

    El mensaje es para el usuario y no lleva datos personales.
    """


@dataclass(frozen=True)
class SourceOptions:
    """Lo que fija el canal. Vacío = se detecta.

    `column_aliases` es `{cabecera del proveedor: campo}`, por ejemplo `{"First name": "nombre"}`.
    """

    format: str
    encoding: str = ""
    delimiter: str = ""
    column_aliases: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RawRecord:
    """Una fila con los valores tal como venían, ya bajo el nombre de su campo.

    `line` es la línea del fichero (1 = cabecera), la que ve el usuario si lo abre.
    """

    line: int
    values: dict[str, Any]
    issues: tuple[Issue, ...] = ()


@dataclass(frozen=True)
class ReadResult:
    records: list[RawRecord]
    columns: dict[str, str]  # campo → cabecera del fichero
    ignored_headers: list[str]


class FormatReader(Protocol):
    """Devuelve las filas del fichero (la primera es la cabecera) sin interpretar los valores.

    Cada fila va con su número de línea. Lanza `SourceError` si el fichero no se puede leer.
    """

    def __call__(
        self, file: BinaryIO, options: SourceOptions
    ) -> Iterator[tuple[int, list[Any]]]: ...
