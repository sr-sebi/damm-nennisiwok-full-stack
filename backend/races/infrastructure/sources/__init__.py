"""Etapas 2 y 3 de la ingesta: lector de formato y mapeo de columnas.

`read_registrations(file, options)` devuelve los registros en bruto con su línea, ya bajo el nombre
de su campo y sin interpretar ningún valor (eso lo hace `races.domain.normalize`). Un formato
nuevo es un lector más en `READERS`.
"""

from __future__ import annotations

from typing import Any, BinaryIO

from races.domain.issues import IssueCode, make_issue
from races.infrastructure.sources.base import (
    FormatReader,
    RawRecord,
    ReadResult,
    SourceError,
    SourceOptions,
)
from races.infrastructure.sources.csv_reader import read_csv
from races.infrastructure.sources.mapping import map_columns
from races.infrastructure.sources.xlsx import read_xlsx

READERS: dict[str, FormatReader] = {
    "xlsx": read_xlsx,
    "csv": read_csv,
}

__all__ = ["RawRecord", "ReadResult", "SourceError", "SourceOptions", "read_registrations"]


def read_registrations(file: BinaryIO, options: SourceOptions) -> ReadResult:
    reader = READERS.get(options.format)
    if reader is None:
        supported = ", ".join(READERS)
        raise SourceError(f"Formato «{options.format}» no soportado (se admiten: {supported}).")

    rows = reader(file, options)
    header_row = next(rows, None)
    if header_row is None:
        raise SourceError("El fichero está vacío.")
    headers = _trim([_header_text(cell) for cell in header_row[1]])
    if not headers:
        raise SourceError("La primera fila (la cabecera) está vacía.")
    positions, ignored = map_columns(headers, options.column_aliases)

    records: list[RawRecord] = []
    for line, cells in rows:
        values = {field: cells[i] if i < len(cells) else None for field, i in positions.items()}
        extra = [cell for cell in cells[len(headers) :] if not _is_empty(cell)]
        issues = ()
        if extra:
            issues = (
                make_issue(
                    IssueCode.TOO_MANY_COLUMNS,
                    "fila",
                    None,
                    found=len(headers) + len(extra),
                    expected=len(headers),
                ),
            )
        records.append(RawRecord(line=line, values=values, issues=issues))

    # Las filas vacías del final (formato aplicado a filas sin datos, líneas en blanco) no son
    # filas del listado. Las de en medio sí se devuelven: se cuentan como vacías.
    while records and not records[-1].issues and all(map(_is_empty, records[-1].values.values())):
        records.pop()
    columns = {field: headers[i] for field, i in positions.items()}
    return ReadResult(records=records, columns=columns, ignored_headers=ignored)


def _header_text(cell: Any) -> str:
    return "" if cell is None else str(cell)


def _is_empty(cell: Any) -> bool:
    return cell is None or (isinstance(cell, str) and not cell.strip())


def _trim(headers: list[str]) -> list[str]:
    while headers and not headers[-1].strip():
        headers.pop()
    return headers
