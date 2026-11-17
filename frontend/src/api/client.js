export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export const NETWORK_ERROR_MESSAGE =
  'No se puede conectar con el servidor. Comprueba la conexión y vuelve a intentarlo.';

// Un 400 de DRF es `{campo: [mensajes]}`: el primer mensaje sirve de resumen.
function firstFieldMessage(data) {
  if (!data || typeof data !== 'object') return null;
  for (const value of Object.values(data)) {
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
    if (typeof value === 'string') return value;
  }
  return null;
}

function messageFor(status, data) {
  if (typeof data?.detail === 'string') return data.detail;
  if (status === 400) return firstFieldMessage(data) ?? 'Hay datos que no son válidos.';
  if (status === 404) return 'No se ha encontrado: puede que ya no exista.';
  if (status >= 500) return 'El servidor ha tenido un problema. Vuelve a intentarlo en un momento.';
  return `La petición no se ha podido completar (código ${status}).`;
}

export async function apiFetch(path, { method = 'GET', body } = {}) {
  const isJson = body !== undefined && !(body instanceof FormData);
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: isJson ? { 'Content-Type': 'application/json' } : undefined,
      body: isJson ? JSON.stringify(body) : body,
    });
  } catch {
    throw new ApiError(NETWORK_ERROR_MESSAGE, 0, null);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // Sin respuesta JSON y con 502/503/504: el proxy no llega al servidor.
    const unreachable = data === null && response.status >= 502;
    const message = unreachable ? NETWORK_ERROR_MESSAGE : messageFor(response.status, data);
    throw new ApiError(message, response.status, data);
  }
  return data;
}

// Errores por campo de un 400 (`{campo: [mensajes]}`) como `{campo: 'mensaje mensaje'}`.
export function fieldErrors(error) {
  if (error?.status !== 400 || !error.data || typeof error.data !== 'object') return {};
  const result = {};
  for (const [field, value] of Object.entries(error.data)) {
    const messages = Array.isArray(value) ? value : [value];
    result[field] = messages.filter((m) => typeof m === 'string').join(' ');
  }
  return result;
}

export function queryString(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}
