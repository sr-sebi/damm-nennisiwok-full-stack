import {
  Alert,
  AlertTitle,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Stack,
} from '@mui/material';
import { useEffect, useRef, useState } from 'react';
import { fieldErrors } from '../api/client';
import { checkRegistration, createRegistration } from '../api/registrations';
import { EMPTY_REGISTRATION, REGISTRATION_FIELDS } from '../utils/labels';
import RegistrationFields from './RegistrationFields';

// Campos que cambian lo que dice la comprobación (ya inscrita / posible duplicado).
const CHECKED_FIELDS = ['email', 'first_name', 'last_name', 'birth_date'];

function checkPayload(values) {
  return Object.fromEntries(
    CHECKED_FIELDS.filter((name) => values[name].trim()).map((name) => [name, values[name]]),
  );
}

// Alta en tienda. Comprueba ANTES de guardar si la persona ya está inscrita (por email), si
// parece la misma que otra (nombre + apellidos + fecha) y si irá a lista de espera.
export default function RegistrationForm({ raceId, channel, onClose, onCreated, onEditExisting }) {
  const [values, setValues] = useState(EMPTY_REGISTRATION);
  const [warnings, setWarnings] = useState({ already: null, duplicate: null });
  const [waitlist, setWaitlist] = useState('');
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState(null);
  const lastCheck = useRef(0);

  const runCheck = async (current) => {
    const id = ++lastCheck.current;
    setChecking(true);
    try {
      const result = await checkRegistration(raceId, checkPayload(current));
      if (id !== lastCheck.current) return; // ya hay otra comprobación más reciente
      setWarnings({ already: result.already_registered, duplicate: result.possible_duplicate });
      // Sin `waitlist` cuando ya está inscrita: se mantiene lo que dijo la anterior.
      if (!result.already_registered) setWaitlist(result.waitlist);
    } catch {
      // Es solo un aviso: si falla, se puede guardar igual y el servidor vuelve a comprobarlo.
    } finally {
      if (id === lastCheck.current) setChecking(false);
    }
  };

  // Al abrir: ¿el aforo está lleno? (para avisar de la lista de espera desde el principio)
  useEffect(() => {
    let ignore = false;
    checkRegistration(raceId, {})
      .then((result) => {
        if (!ignore) setWaitlist(result.waitlist);
      })
      .catch(() => {});
    return () => {
      ignore = true;
    };
  }, [raceId]);

  const handleChange = (name, value) => {
    setValues((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name]: undefined }));
    if (name === 'email') setWarnings((current) => ({ ...current, already: null }));
    if (['first_name', 'last_name', 'birth_date'].includes(name)) {
      setWarnings((current) => ({ ...current, duplicate: null }));
    }
  };

  const handleBlur = (name) => {
    const hasIdentity = values.first_name.trim() && values.last_name.trim() && values.birth_date;
    if (name === 'email' && values.email.trim()) runCheck(values);
    else if (['first_name', 'last_name', 'birth_date'].includes(name) && hasIdentity) {
      runCheck(values);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    setError(null);
    try {
      const result = await createRegistration(raceId, { channel: channel.code, ...values });
      onCreated(result);
    } catch (err) {
      if (err.status === 409) {
        setWarnings((current) => ({
          ...current,
          already: { message: err.message, registration: err.data?.registration },
        }));
      } else {
        const byField = fieldErrors(err);
        setErrors(byField);
        const others = Object.keys(byField).filter((name) => !REGISTRATION_FIELDS.includes(name));
        if (Object.keys(byField).length === 0) setError(err.message);
        else if (others.length) setError(others.map((name) => byField[name]).join(' '));
      }
    } finally {
      setSaving(false);
    }
  };

  const already = warnings.already;

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <form onSubmit={handleSubmit} noValidate>
        <DialogTitle>Alta en {channel.name.toLowerCase()}</DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            {waitlist && !already && (
              <Alert severity="warning">
                <AlertTitle>Irá a la lista de espera</AlertTitle>
                {waitlist}
              </Alert>
            )}
            {error && <Alert severity="error">{error}</Alert>}
            <RegistrationFields
              values={values}
              errors={errors}
              helpers={{ birth_date: 'Día, mes y año (se guarda como AAAA-MM-DD).' }}
              onChange={handleChange}
              onBlur={handleBlur}
            />
            {checking && <LinearProgress aria-label="Comprobando si ya está inscrita" />}
            {already && (
              <Alert
                severity="error"
                action={
                  already.registration && (
                    <Button
                      color="inherit"
                      size="small"
                      onClick={() => onEditExisting(already.registration.id)}
                    >
                      Editar su inscripción
                    </Button>
                  )
                }
              >
                <AlertTitle>Ya está inscrita en esta carrera</AlertTitle>
                {already.message} No se puede dar de alta otra vez: si hay que cambiar algún dato,
                edita su inscripción.
              </Alert>
            )}
            {warnings.duplicate && (
              <Alert
                severity="warning"
                action={
                  warnings.duplicate.registration && (
                    <Button
                      color="inherit"
                      size="small"
                      onClick={() => onEditExisting(warnings.duplicate.registration.id)}
                    >
                      Ver la otra
                    </Button>
                  )
                }
              >
                <AlertTitle>¿Es la misma persona?</AlertTitle>
                {warnings.duplicate.message}
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancelar</Button>
          <Button type="submit" variant="contained" disabled={saving || Boolean(already)}>
            {saving ? 'Guardando…' : waitlist ? 'Apuntar en lista de espera' : 'Dar de alta'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
