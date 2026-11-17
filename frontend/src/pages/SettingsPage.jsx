import SaveIcon from '@mui/icons-material/Save';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useState } from 'react';
import { getSettings, listJobRuns, saveSettings } from '../api/settings';
import { formatDateTime } from '../utils/format';

const PLACEHOLDERS = ['{nombre}', '{dorsal}', '{carrera}', '{fecha}'];

const RESULT_COLOR = {
  ok: 'success',
  error: 'error',
  locked: 'warning',
  caido: 'warning',
  en_marcha: 'info',
};

function networkMessage(err) {
  return err.status ? err.message : 'No se ha podido conectar con el servidor.';
}

function errorText(errors, field) {
  const value = errors?.[field];
  return Array.isArray(value) ? value.join(' ') : value;
}

export default function SettingsPage() {
  const [form, setForm] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});
  const [saved, setSaved] = useState(false);

  const fetchAll = useCallback(
    (isCurrent = () => true) =>
      Promise.all([getSettings(), listJobRuns()])
        .then(([settings, jobRuns]) => {
          if (!isCurrent()) return;
          setForm(settings);
          setRuns(jobRuns);
          setLoadError(null);
        })
        .catch((err) => {
          if (isCurrent()) setLoadError(networkMessage(err));
        })
        .finally(() => {
          if (isCurrent()) setLoading(false);
        }),
    [],
  );

  useEffect(() => {
    let current = true;
    fetchAll(() => current);
    return () => {
      current = false;
    };
  }, [fetchAll]);

  const load = () => {
    setLoading(true);
    fetchAll();
  };

  const set = (field) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
    setForm((current) => ({ ...current, [field]: value }));
    setSaved(false);
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    setSaved(false);
    saveSettings({
      auto_send_enabled: form.auto_send_enabled,
      auto_send_time: form.auto_send_time,
      email_subject: form.email_subject,
      email_body: form.email_body,
      send_rate_per_second: Number(form.send_rate_per_second),
      max_attempts: Number(form.max_attempts),
      import_stale_minutes: Number(form.import_stale_minutes),
    })
      .then((settings) => {
        setForm(settings);
        setSaved(true);
      })
      .catch((err) => {
        if (err.status === 400 && err.data) setErrors(err.data);
        else setErrors({ general: networkMessage(err) });
      })
      .finally(() => setSaving(false));
  };

  if (loading && !form) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }
  if (loadError && !form) {
    return (
      <Alert
        severity="error"
        action={
          <Button color="inherit" onClick={load}>
            Reintentar
          </Button>
        }
      >
        No se ha podido cargar la configuración: {loadError}
      </Alert>
    );
  }

  const last = form.last_scheduled_send;

  return (
    <>
      <Typography variant="h4" component="h1" sx={{ mb: 3 }}>
        Configuración
      </Typography>

      <Paper variant="outlined" sx={{ p: 3, mb: 3 }} component="form" onSubmit={handleSubmit}>
        <Stack spacing={3}>
          {errors.general && <Alert severity="error">{errors.general}</Alert>}
          {saved && <Alert severity="success">Configuración guardada. Vale desde el próximo minuto.</Alert>}

          <Box>
            <Typography variant="h6" gutterBottom>
              Envío de confirmaciones
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Proveedor de email: <strong>{form.email_provider}</strong> (se cambia en la
              instalación, no aquí).
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
              <FormControlLabel
                control={<Switch checked={form.auto_send_enabled} onChange={set('auto_send_enabled')} />}
                label="Enviar automáticamente cada día"
              />
              <TextField
                label="Hora"
                type="time"
                value={form.auto_send_time}
                onChange={set('auto_send_time')}
                error={Boolean(errors.auto_send_time)}
                helperText={errorText(errors, 'auto_send_time') || 'Hora local de la península'}
                slotProps={{ inputLabel: { shrink: true } }}
              />
            </Stack>
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Último envío programado:{' '}
                {last ? (
                  <>
                    {formatDateTime(last.started_at)}{' '}
                    <Chip
                      size="small"
                      label={last.result_display}
                      color={RESULT_COLOR[last.result] ?? 'default'}
                    />{' '}
                    {last.summary}
                  </>
                ) : (
                  'todavía no se ha hecho ninguno.'
                )}
              </Typography>
            </Box>
          </Box>

          <Box>
            <Typography variant="h6" gutterBottom>
              Plantilla del email
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Puedes usar {PLACEHOLDERS.join(', ')}.
            </Typography>
            <Stack spacing={2}>
              <TextField
                label="Asunto"
                value={form.email_subject}
                onChange={set('email_subject')}
                error={Boolean(errors.email_subject)}
                helperText={errorText(errors, 'email_subject')}
                fullWidth
              />
              <TextField
                label="Cuerpo"
                value={form.email_body}
                onChange={set('email_body')}
                error={Boolean(errors.email_body)}
                helperText={errorText(errors, 'email_body')}
                multiline
                minRows={6}
                fullWidth
              />
            </Stack>
          </Box>

          <Box>
            <Typography variant="h6" gutterBottom>
              Ritmo y reintentos
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label="Emails por segundo"
                type="number"
                value={form.send_rate_per_second}
                onChange={set('send_rate_per_second')}
                error={Boolean(errors.send_rate_per_second)}
                helperText={errorText(errors, 'send_rate_per_second') || 'Entre 1 y 19'}
                slotProps={{ htmlInput: { min: 1, max: 19 } }}
              />
              <TextField
                label="Intentos por email"
                type="number"
                value={form.max_attempts}
                onChange={set('max_attempts')}
                error={Boolean(errors.max_attempts)}
                helperText={errorText(errors, 'max_attempts')}
                slotProps={{ htmlInput: { min: 1, max: 20 } }}
              />
              <TextField
                label="Minutos para dar por caída una importación"
                type="number"
                value={form.import_stale_minutes}
                onChange={set('import_stale_minutes')}
                error={Boolean(errors.import_stale_minutes)}
                helperText={errorText(errors, 'import_stale_minutes')}
                slotProps={{ htmlInput: { min: 1, max: 1440 } }}
              />
            </Stack>
          </Box>

          <Box>
            <Button type="submit" variant="contained" startIcon={<SaveIcon />} disabled={saving}>
              {saving ? 'Guardando…' : 'Guardar'}
            </Button>
          </Box>
        </Stack>
      </Paper>

      <Typography variant="h6" gutterBottom>
        Últimas ejecuciones programadas
      </Typography>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small" aria-label="Últimas ejecuciones programadas">
          <TableHead>
            <TableRow>
              <TableCell>Empezó</TableCell>
              <TableCell>Trabajo</TableCell>
              <TableCell>Resultado</TableCell>
              <TableCell>Resumen</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {runs.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                  Todavía no se ha ejecutado nada.
                </TableCell>
              </TableRow>
            )}
            {runs.map((run) => (
              <TableRow key={run.id}>
                <TableCell>{formatDateTime(run.started_at)}</TableCell>
                <TableCell>{run.job_display}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={run.result_display}
                    color={RESULT_COLOR[run.result] ?? 'default'}
                  />
                </TableCell>
                <TableCell>{run.summary}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}
