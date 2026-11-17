import { apiFetch, queryString } from './client';

// `page` empieza en 1; 50 por página.
export const listRegistrations = (raceId, { q, status, page }) =>
  apiFetch(`/races/${raceId}/registrations/${queryString({ q, status, page })}`);

// POST para que el email no vaya en la URL. Solo lee.
export const checkRegistration = (raceId, data) =>
  apiFetch(`/races/${raceId}/registrations/check/`, { method: 'POST', body: data });

export const createRegistration = (raceId, data) =>
  apiFetch(`/races/${raceId}/registrations/`, { method: 'POST', body: data });

export const getRegistration = (registrationId) => apiFetch(`/registrations/${registrationId}/`);

export const updateRegistration = (registrationId, changes) =>
  apiFetch(`/registrations/${registrationId}/`, { method: 'PATCH', body: changes });

export const withdrawRegistration = (registrationId) =>
  apiFetch(`/registrations/${registrationId}/withdraw/`, { method: 'POST' });

export const clearPossibleDuplicate = (registrationId) =>
  apiFetch(`/registrations/${registrationId}/not-duplicate/`, { method: 'POST' });
