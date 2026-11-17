import {
  Alert,
  AlertTitle,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { fieldErrors } from '../api/client';
import { getRegistration, updateRegistration } from '../api/registrations';
import { REGISTRATION_FIELDS, registrationStatusLabel } from '../utils/labels';
import RegistrationFields from './RegistrationFields';

function valuesOf(registration) {
  return Object.fromEntries(REGISTRATION_FIELDS.map((name) => [name, registration[name] ?? '']));
}

function Loaded({ registration, onClose, onSaved }) {
  const original = valuesOf(registration);
  const [values, setValues] = useState(original);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);
  const online = registration.channel?.kind === 'plataforma_online';

  const handleSubmit = async (event) => {
    event.preventDefault();
    // Solo lo que se ha tocado: lo demás no cambia.
    const changes = Object.fromEntries(
      REGISTRATION_FIELDS.filter((name) => values[name] !== original[name]).map((name) => [
        name,
        values[name],
      ]),
    );
    if (Object.keys(changes).length === 0) {
      setDone({ changes: [], notice: '' });
      return;
    }
    setSaving(true);
    setErrors({});
    setError(null);
    try {
      const result = await updateRegistration(registration.id, changes);
      setDone(result);
      onSaved(result);
    } catch (err) {
      const byField = fieldErrors(err);
      setErrors(byField);
      const fieldNames = Object.keys(byField).filter((name) => REGISTRATION_FIELDS.includes(name));
      setError(fieldNames.length && fieldNames.length === Object.keys(byField).length ? null : err.message);
    } finally {
      setSaving(false);
    }
  };

  if (done) {
    return (
      <>
        <DialogContent>
          <Stack spacing={2}>
            {done.changes.length ? (
              <Alert severity="success">
                <AlertTitle>Datos corregidos</AlertTitle>
                <Box component="ul" sx={{ m: 0, pl: 2 }}>
                  {done.changes.map((change) => (
                    <li key={change}>{change}</li>
                  ))}
                </Box>
              </Alert>
            ) : (
              <Alert severity="info">No había nada que cambiar.</Alert>
            )}
            {done.notice && <Alert severity="warning">{done.notice}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button variant="contained" onClick={onClose}>
            Cerrar
          </Button>
        </DialogActions>
      </>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <DialogContent>
        <Stack spacing={2}>
          <Alert severity="info" icon={false}>
            {registration.channel?.name} · {registrationStatusLabel(registration)}
            {registration.bib != null && ` · dorsal ${registration.bib}`}. El dorsal, el estado y
            el canal no se cambian desde aquí.
          </Alert>
          {error && <Alert severity="error">{error}</Alert>}
          <RegistrationFields
            values={values}
            errors={errors}
            helpers={
              online
                ? {
                    email: `Llega del listado de ${registration.channel.name}: el email se cambia en la plataforma.`,
                  }
                : {}
            }
            onChange={(name, value) => setValues((current) => ({ ...current, [name]: value }))}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button type="submit" variant="contained" disabled={saving}>
          {saving ? 'Guardando…' : 'Guardar cambios'}
        </Button>
      </DialogActions>
    </form>
  );
}

// Corregir los datos de una inscripción. Se abre con su id (desde la tabla o desde el aviso
// «ya inscrita» del alta en tienda).
export default function EditRegistrationDialog({ registrationId, onClose, onSaved }) {
  const [result, setResult] = useState({ id: null, data: null, error: null });

  useEffect(() => {
    let ignore = false;
    getRegistration(registrationId)
      .then((data) => {
        if (!ignore) setResult({ id: registrationId, data, error: null });
      })
      .catch((err) => {
        if (!ignore) setResult({ id: registrationId, data: null, error: err.message });
      });
    return () => {
      ignore = true;
    };
  }, [registrationId]);

  const registration = result.id === registrationId ? result.data : null;

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>
        Corregir datos
        {registration && ` de ${registration.first_name} ${registration.last_name}`}
      </DialogTitle>
      {result.error && result.id === registrationId && (
        <>
          <DialogContent>
            <Alert severity="error">No se pudo cargar la inscripción: {result.error}</Alert>
          </DialogContent>
          <DialogActions>
            <Button onClick={onClose}>Cerrar</Button>
          </DialogActions>
        </>
      )}
      {!registration && !(result.error && result.id === registrationId) && (
        <DialogContent>
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress aria-label="Cargando la inscripción" />
          </Box>
        </DialogContent>
      )}
      {registration && <Loaded registration={registration} onClose={onClose} onSaved={onSaved} />}
    </Dialog>
  );
}
