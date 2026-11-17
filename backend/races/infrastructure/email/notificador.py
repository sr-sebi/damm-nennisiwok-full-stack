"""Adaptador del Notificador (docs/notificador.md), con `urllib` de la librería estándar.

Traducción de sus respuestas:

- 202 (o cualquier 2xx) → `Accepted` con el id del mensaje. Una clave repetida devuelve 202 con
  `Idempotent-Replayed: true` y no envía: también es `Accepted`.
- 429 → `RetryLater(Retry-After)`: espera lo que dice y no gasta intento.
- 5xx, sin respuesta en `TIMEOUT_SECONDS` y error de red → `RetryLater()`. Medido contra el
  simulador: una petición que no responde a tiempo puede haberse aceptado, y un 500 no guarda la
  clave; por eso el reintento va siempre con la misma `Idempotency-Key`.
- 400 y otros 4xx → `Rejected` con el motivo que da.
- 401, 403 y 404 (API key, permisos o URL mal configuradas) → `ConfigError`.

Ni los logs ni los motivos llevan el email del destinatario.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from races.infrastructure.email.base import (
    Accepted,
    ConfigError,
    EmailProvider,
    Rejected,
    RetryLater,
    SendResult,
)

# Las respuestas lentas del simulador tardan 3 s; el proxy de producción corta a 30 s, pero esto
# va en el worker, no en una petición.
TIMEOUT_SECONDS = 10
# 429 sin `Retry-After` (el simulador siempre lo manda): un segundo, como su ventana.
DEFAULT_RETRY_AFTER = 1.0
CONFIG_STATUSES = {401: "API key incorrecta", 403: "sin permiso", 404: "URL incorrecta"}


class NotificadorProvider(EmailProvider):
    name = "notificador"

    def __init__(self, base_url: str, api_key: str, timeout: float = TIMEOUT_SECONDS):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout

    def send(self, to: str, subject: str, body: str, idempotency_key: str) -> SendResult:
        if not self.base_url or not self.api_key:
            return ConfigError(
                "Falta la URL o la API key del Notificador (NOTIFIER_BASE_URL, NOTIFIER_API_KEY)."
            )
        payload = {"channel": "email", "to": to, "subject": subject, "body": body}
        request = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "Idempotency-Key": idempotency_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return _accepted(response.read())
        except urllib.error.HTTPError as exc:
            return _from_error_status(exc)
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                return _timed_out(self.timeout)
            return RetryLater(reason=f"Error de red con el Notificador ({_kind(exc.reason)}).")
        except TimeoutError:
            return _timed_out(self.timeout)
        except ValueError:
            return ConfigError(f"La URL del Notificador no es válida: «{self.base_url}».")
        except OSError as exc:  # conexión cortada a mitad de respuesta, etc.
            return RetryLater(reason=f"Error de red con el Notificador ({_kind(exc)}).")


def _accepted(raw: bytes) -> Accepted:
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        data = {}
    provider_id = data.get("id", "") if isinstance(data, dict) else ""
    return Accepted(provider_id=str(provider_id)[:255])


def _from_error_status(exc: urllib.error.HTTPError) -> SendResult:
    status = exc.code
    detail = _detail(exc)
    if status == 429:
        return RetryLater(
            after_seconds=_retry_after(exc.headers.get("Retry-After")),
            reason="El Notificador pide esperar (429: demasiadas peticiones por segundo).",
        )
    if status >= 500:
        return RetryLater(reason=f"Error del Notificador ({status}).")
    if status in CONFIG_STATUSES:
        return ConfigError(
            f"El Notificador responde {status} ({CONFIG_STATUSES[status]}): revisa "
            "NOTIFIER_BASE_URL y NOTIFIER_API_KEY."
        )
    suffix = f": {detail}" if detail else ""
    return Rejected(f"El Notificador rechaza el mensaje ({status}){suffix}.")


def _detail(exc: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(exc.read() or b"{}")
    except (ValueError, OSError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("detail") or data.get("error") or "")[:300]


def _retry_after(value: str | None) -> float:
    """`Retry-After` en segundos o como fecha HTTP. Si no se entiende, `DEFAULT_RETRY_AFTER`."""
    if not value:
        return DEFAULT_RETRY_AFTER
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def _timed_out(timeout: float) -> RetryLater:
    return RetryLater(
        reason=(
            f"El Notificador no ha respondido en {timeout:g} s. Puede que lo aceptara: se "
            "reintenta con la misma clave, así que no llegará dos veces."
        )
    )


def _kind(error: object) -> str:
    # Solo el tipo: el texto de un error de red puede llevar la URL con datos.
    return type(error).__name__
