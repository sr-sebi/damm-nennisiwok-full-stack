import { apiFetch } from './client';

export const getSettings = () => apiFetch('/settings/');

export const saveSettings = (settings) => apiFetch('/settings/', { method: 'PUT', body: settings });

export const listJobRuns = () => apiFetch('/job-runs/');
