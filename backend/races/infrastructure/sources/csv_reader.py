"""Lector de CSV: codificación y separador los fija el canal o se detectan.

Detección sin adivinar con librerías: UTF-8 (con o sin BOM) y, si no lo es, cp1252, que es lo que
guarda Excel en Windows. El separador se elige en la línea de cabecera entre `;`, `,` y tabulador.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from typing import Any, BinaryIO

from races.infrastructure.sources.base import SourceError, SourceOptions

DETECTED_ENCODINGS = ("utf-8-sig", "cp1252")
CANDIDATE_DELIMITERS = (";", ",", "\t")
_ZIP_MAGIC = b"PK\x03\x04"


def read_csv(file: BinaryIO, options: SourceOptions) -> Iterator[tuple[int, list[Any]]]:
    data = file.read()
    if data.startswith(_ZIP_MAGIC):
        raise SourceError("El fichero parece un Excel (.xlsx), pero este canal espera un CSV.")
    text = _decode(data, options.encoding)
    delimiter = options.delimiter or _detect_delimiter(text)

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    next_line = 1
    try:
        for row in reader:
            # Una celda entre comillas puede ocupar varias líneas: la fila empieza en la siguiente
            # a donde acabó la anterior.
            yield next_line, row
            next_line = reader.line_num + 1
    except csv.Error as exc:
        raise SourceError(f"El CSV está mal formado cerca de la línea {next_line}.") from exc


def _decode(data: bytes, encoding: str) -> str:
    if encoding:
        try:
            return data.decode(encoding)
        except LookupError as exc:
            raise SourceError(f"La codificación «{encoding}» del canal no existe.") from exc
        except UnicodeDecodeError as exc:
            raise SourceError(
                f"El fichero no está en la codificación del canal ({encoding})."
            ) from exc
    for candidate in DETECTED_ENCODINGS:
        try:
            return data.decode(candidate)
        except UnicodeDecodeError:
            continue
    raise SourceError("No se reconoce la codificación del fichero (ni UTF-8 ni Windows-1252).")


def _detect_delimiter(text: str) -> str:
    header = text.split("\n", 1)[0]
    counts = {delimiter: header.count(delimiter) for delimiter in CANDIDATE_DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","
