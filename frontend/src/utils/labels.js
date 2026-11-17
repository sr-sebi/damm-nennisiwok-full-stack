// Textos de la interfaz para los valores que devuelve la API.

export const SHIRT_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL'];

// Campos de datos de una inscripción (alta en tienda y corrección), con los nombres de la API.
export const EMPTY_REGISTRATION = {
  first_name: '',
  last_name: '',
  email: '',
  birth_date: '',
  phone: '',
  shirt_size: '',
};

export const REGISTRATION_FIELDS = Object.keys(EMPTY_REGISTRATION);

export const REGISTRATION_STATUSES = [
  { value: 'confirmada', label: 'Confirmadas' },
  { value: 'en_espera', label: 'En lista de espera' },
  { value: 'baja', label: 'Bajas' },
];

export function registrationStatusLabel(registration) {
  switch (registration.status) {
    case 'confirmada':
      return 'Confirmada';
    case 'en_espera':
      return registration.waitlist_position
        ? `En espera (n.º ${registration.waitlist_position})`
        : 'En espera';
    case 'baja':
      return 'Baja';
    default:
      return registration.status;
  }
}

// «Plataforma B, dorsal 9» a partir del resumen de una inscripción.
export function describeSummary(summary) {
  if (!summary) return '';
  const name = `${summary.first_name} ${summary.last_name}`;
  if (summary.status === 'en_espera') {
    return `${name} (${summary.channel}, en lista de espera, n.º ${summary.waitlist_position})`;
  }
  if (summary.status === 'baja') return `${name} (${summary.channel}, dada de baja)`;
  return `${name} (${summary.channel}, dorsal ${summary.bib})`;
}

export const IMPORT_PHASES = {
  en_cola: 'En cola',
  leyendo: 'Leyendo y comprobando el fichero',
  guardando: 'Guardando inscripciones',
  comprobando_ausencias: 'Comprobando quién ya no aparece en el listado',
  hecho: 'Terminada',
  error: 'Con error',
};

export const isImportActive = (batch) => batch.status === 'en_cola' || batch.status === 'procesando';

export const formatNumber = (value) => (value ?? 0).toLocaleString('es-ES');

// `raw` de una incidencia: la fila tal como llegó, en JSON. Para reconocer a la persona.
export function describeRaw(raw) {
  if (!raw) return '';
  let values;
  try {
    values = JSON.parse(raw);
  } catch {
    return raw;
  }
  if (!values || typeof values !== 'object') return String(raw);
  const pick = (...keys) => keys.map((k) => values[k]).find((v) => v);
  const name = [pick('nombre', 'first_name'), pick('apellidos', 'last_name')]
    .filter(Boolean)
    .join(' ');
  const email = pick('email');
  const text = [name, email].filter(Boolean).join(' · ');
  if (text) return text;
  return Object.values(values).filter(Boolean).join(' · ') || '(fila vacía)';
}

// «Talla: M → L; Email: a → b» → ['Talla: M → L', 'Email: a → b'].
export const splitDifferences = (text) =>
  (text || '')
    .split('; ')
    .map((part) => part.trim())
    .filter(Boolean);
