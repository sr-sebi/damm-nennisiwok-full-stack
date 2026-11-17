"""Interfaz de un proveedor de email y los cuatro resultados posibles de un envío.

Un adaptador traduce las respuestas de su proveedor a estos resultados y no decide nada más: la
política de reintentos, el ritmo y la bandeja de salida viven en `races.application`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Accepted:
    """El proveedor ha aceptado el mensaje (o ya lo tenía con esa clave)."""

    provider_id: str = ""


@dataclass(frozen=True)
class RetryLater:
    """No se sabe si ha salido o no ha salido: se reintenta con la misma clave.

    `after_seconds` lo da el proveedor cuando dice cuánto esperar (un 429 con `Retry-After`): es un
    «espera», no un fallo, y no gasta intento. Sin él (error 5xx, sin respuesta a tiempo, red), la
    espera la decide la bandeja de salida y sí gasta intento.
    """

    after_seconds: float | None = None
    reason: str = ""


@dataclass(frozen=True)
class Rejected:
    """El proveedor no lo enviará nunca (email mal formado…): reintentar no sirve."""

    reason: str


@dataclass(frozen=True)
class ConfigError:
    """Falla la configuración (credenciales, URL, proveedor desconocido): no es culpa del mensaje.

    Se para el lote sin gastar intentos: cuando se arregle, se envía igual.
    """

    reason: str


SendResult = Accepted | RetryLater | Rejected | ConfigError


class EmailProvider(ABC):
    """Un proveedor de email. Cambiar de proveedor = una subclase y `EMAIL_PROVIDER` en el entorno.

    `idempotency_key` identifica el mensaje lógico y es la misma en todos sus intentos. Si un
    proveedor no tiene idempotencia, su adaptador tiene que decirlo: la protección contra
    duplicados sigue siendo el estado en la base de datos, salvo en el caso «sin respuesta a
    tiempo», en el que no se puede saber si salió.
    """

    name: str = ""

    @abstractmethod
    def send(self, to: str, subject: str, body: str, idempotency_key: str) -> SendResult:
        """Envía un mensaje. No lanza excepciones: todo acaba en uno de los cuatro resultados."""
