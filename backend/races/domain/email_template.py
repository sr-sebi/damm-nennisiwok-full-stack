"""Plantilla del email de confirmación: marcadores permitidos, validación y relleno.

La plantilla la escribe la organización (asunto y cuerpo), así que se valida al guardarla y no al
enviar: un marcador desconocido como `{dni}` o una llave sin cerrar se explican en español.
Solo valen marcadores simples (`{nombre}`), sin formato (`{dorsal:05}`) ni atributos
(`{nombre.upper}`): con `str.format` un atributo daría acceso a objetos de Python.

Los valores (nombre, carrera…) son datos del corredor y no se vuelven a interpretar: una llave en
un nombre sale tal cual.
"""

from __future__ import annotations

from collections.abc import Mapping
from string import Formatter

PLACEHOLDERS = ("nombre", "dorsal", "carrera", "fecha")

DEFAULT_SUBJECT = "Inscripción confirmada: {carrera}, dorsal {dorsal}"
DEFAULT_BODY = (
    "Hola, {nombre}:\n"
    "\n"
    "Tu inscripción en {carrera} está confirmada. Tu dorsal es el {dorsal}.\n"
    "\n"
    "La carrera es el {fecha}. ¡Nos vemos en la salida!\n"
    "\n"
    "Un saludo,\n"
    "La organización"
)

_ALLOWED = ", ".join(f"{{{name}}}" for name in PLACEHOLDERS)


def template_errors(text: str) -> list[str]:
    """Errores de una plantilla, para el usuario. Lista vacía = se puede usar."""
    try:
        parts = list(Formatter().parse(text or ""))
    except ValueError:
        return [
            "Hay una llave sin cerrar o sin abrir. Los marcadores van entre llaves, como "
            "{nombre}; para escribir una llave en el texto, ponla doble: {{ o }}."
        ]
    errors: list[str] = []
    for _literal, field, spec, conversion in parts:
        if field is None:
            continue
        shown = (
            "{" + field + (f"!{conversion}" if conversion else "") + (f":{spec}" if spec else "")
        )
        shown += "}"
        if field == "":
            message = (
                f"Hay unas llaves vacías ({shown}). Marcadores que se pueden usar: {_ALLOWED}."
            )
        elif field not in PLACEHOLDERS:
            message = f"El marcador {shown} no existe. Marcadores que se pueden usar: {_ALLOWED}."
        elif spec or conversion:
            message = f"El marcador {shown} no admite formato: escríbelo como {{{field}}}."
        else:
            continue
        if message not in errors:
            errors.append(message)
    return errors


def render(template: str, values: Mapping[str, object]) -> str:
    """Rellena la plantilla. Una plantilla con errores da `ValueError` (se valida al guardarla)."""
    errors = template_errors(template)
    if errors:
        raise ValueError(" ".join(errors))
    return template.format_map({name: str(values.get(name, "")) for name in PLACEHOLDERS})
