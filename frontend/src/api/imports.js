import { apiFetch } from './client';

export function uploadImport(raceId, channelCode, file) {
  const body = new FormData();
  body.append('channel', channelCode);
  body.append('file', file);
  return apiFetch(`/races/${raceId}/imports/`, { method: 'POST', body });
}

// Las últimas 20, la más reciente primero, con fase, porcentaje y cola.
export const listImports = (raceId) => apiFetch(`/races/${raceId}/imports/`);

// La importación con su informe (`issue_groups`).
export const getImport = (importId) => apiFetch(`/imports/${importId}/`);

// Todas las incidencias de un grupo, 50 por página. `page` empieza en 1.
// Los filtros van aunque estén vacíos: `value=` (sin valor) también es un grupo.
export function listImportIssues(importId, { kind, code, field, value, page }) {
  const params = new URLSearchParams({ kind, code, field, value, page: String(page) });
  return apiFetch(`/imports/${importId}/issues/?${params}`);
}
