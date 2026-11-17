"""Lector de Excel (.xlsx) con openpyxl en modo de solo lectura.

Las celdas llegan con su tipo: una celda de fecha es `datetime` y un teléfono numérico es `int`.
Interpretarlas es cosa del normalizador.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from typing import Any, BinaryIO

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from races.infrastructure.sources.base import SourceError, SourceOptions


def read_xlsx(file: BinaryIO, options: SourceOptions) -> Iterator[tuple[int, list[Any]]]:
    try:
        workbook = load_workbook(file, read_only=True, data_only=True)
    except (zipfile.BadZipFile, InvalidFileException, KeyError, OSError, ValueError) as exc:
        raise SourceError("El fichero no es un Excel .xlsx válido.") from exc
    try:
        if not workbook.worksheets:
            raise SourceError("El Excel no tiene ninguna hoja.")
        # Se lee la primera hoja: las muestras traen una sola.
        sheet = workbook.worksheets[0]
        # La dimensión guardada en el fichero puede estar mal (algunos programas escriben A1):
        # sin ella se leen todas las filas que haya.
        sheet.reset_dimensions()
        # openpyxl rellena las filas que faltan en el fichero, así que el contador es la fila.
        for line, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            yield line, list(row)
    finally:
        workbook.close()
