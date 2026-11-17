import { apiFetch } from './client';

// { race, race_past, provider, pending, sending, sent, failed, held_duplicates, failures: [...] }
export const getConfirmations = (raceId) => apiFetch(`/races/${raceId}/confirmations/`);

// 202 { queued: true, pending, message } · 200 { queued: false, pending: 0, message } · 400 { detail }
export const sendConfirmations = (raceId) =>
  apiFetch(`/races/${raceId}/confirmations/`, { method: 'POST' });

// 202 { notification, message } · 409 { detail }
export const retryNotification = (notificationId) =>
  apiFetch(`/notifications/${notificationId}/retry/`, { method: 'POST' });
