"""Proveedores de email intercambiables.

El activo se elige por nombre con `settings.EMAIL_PROVIDER` (variable de entorno, por defecto
«notificador»); sus credenciales y su URL van también en el entorno, nunca en la base de datos.
Un proveedor nuevo es una subclase de `EmailProvider` y una entrada en `PROVIDERS`.
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings

from races.infrastructure.email.base import (
    Accepted,
    ConfigError,
    EmailProvider,
    Rejected,
    RetryLater,
    SendResult,
)
from races.infrastructure.email.notificador import NotificadorProvider

PROVIDERS: dict[str, Callable[[], EmailProvider]] = {
    "notificador": lambda: NotificadorProvider(
        settings.NOTIFIER_BASE_URL, settings.NOTIFIER_API_KEY
    ),
}


class UnknownProvider(Exception):
    """`EMAIL_PROVIDER` no es ninguno de los conocidos. El mensaje es para el usuario."""


def active_provider_name() -> str:
    return (settings.EMAIL_PROVIDER or "").strip().lower()


def get_provider(name: str | None = None) -> EmailProvider:
    name = (name or active_provider_name()).strip().lower()
    factory = PROVIDERS.get(name)
    if factory is None:
        known = ", ".join(sorted(PROVIDERS))
        raise UnknownProvider(
            f"El proveedor de email «{name}» (EMAIL_PROVIDER) no existe; los que hay: {known}."
        )
    return factory()


__all__ = [
    "PROVIDERS",
    "Accepted",
    "ConfigError",
    "EmailProvider",
    "Rejected",
    "RetryLater",
    "SendResult",
    "UnknownProvider",
    "active_provider_name",
    "get_provider",
]
