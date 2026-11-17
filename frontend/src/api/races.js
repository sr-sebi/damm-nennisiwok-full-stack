import { apiFetch } from './client';

export const listRaces = () => apiFetch('/races/');

export const getRace = (raceId) => apiFetch(`/races/${raceId}/`);

export const createRace = (race) => apiFetch('/races/', { method: 'POST', body: race });

// Solo el aforo (null = sin límite). Devuelve la carrera más `promoted` y `message`.
export const updateRaceCapacity = (raceId, capacity) =>
  apiFetch(`/races/${raceId}/`, { method: 'PATCH', body: { capacity } });

export const listChannels = () => apiFetch('/channels/');

export const getRaceStats = (raceId) => apiFetch(`/races/${raceId}/stats/`);
