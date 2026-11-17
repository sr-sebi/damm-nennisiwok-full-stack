import ReplayIcon from '@mui/icons-material/Replay';
import SendIcon from '@mui/icons-material/Send';
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getConfirmations, retryNotification, sendConfirmations } from '../api/confirmations';
import { formatDateTime } from '../utils/format';

const POLL_MS = 2000;

// Emails de confirmación de una carrera: botón de envío, cómo va y las fallidas con su motivo.
// `onChange` se llama cuando cambia algo (para que la página recargue la tabla, si quiere).
export default function ConfirmationsPanel({ raceId, onChange }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [following, setFollowing] = useState(false);
  const onChangeRef = useRef(onChange);
  // Último envío con el botón que ya conocíamos: el seguimiento para cuando llega uno nuevo.
  const lastSendSeen = useRef(undefined);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  const load = useCallback(async () => {
    try {
      const next = await getConfirmations(raceId);
      setData(next);
      setError(null);
      return next;
    } catch (err) {
      setError(err.message);
      return null;
    }
  }, [raceId]);

  useEffect(() => {
    let ignore = false;
    getConfirmations(raceId)
      .then((next) => {
        if (!ignore) setData(next);
      })
      .catch((err) => {
        if (!ignore) setError(err.message);
      });
    return () => {
      ignore = true;
    };
  }, [raceId]);

  // Mientras hay un envío en marcha, se sondea hasta que no quede nada pendiente.
  useEffect(() => {
    if (!following) return undefined;
    const timer = setInterval(async () => {
      const next = await load();
      if (!next) return;
      const finished = next.last_send && next.last_send.id !== lastSendSeen.current;
      if (finished) {
        lastSendSeen.current = next.last_send.id;
        const failedRun = next.last_send.result === 'error';
        const later = !failedRun && next.pending > 0 ? ' Las que faltan se reintentarán solas.' : '';
        setNotice({
          severity: failedRun ? 'error' : 'success',
          text: `${failedRun ? 'El envío se ha parado: ' : 'Envío terminado: '}${next.last_send.summary}${later}`,
        });
      }
      if (finished || (next.pending === 0 && next.sending === 0)) {
        setFollowing(false);
        onChangeRef.current?.();
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [following, load]);

  const handleSend = async () => {
    lastSendSeen.current = data?.last_send?.id ?? null;
    setBusy(true);
    setNotice(null);
    try {
      const result = await sendConfirmations(raceId);
      setNotice({ severity: result.queued ? 'info' : 'success', text: result.message });
      if (result.queued) setFollowing(true);
      await load();
    } catch (err) {
      setNotice({ severity: 'error', text: err.message });
    } finally {
      setBusy(false);
    }
  };

  const handleRetry = async (notificationId) => {
    lastSendSeen.current = data?.last_send?.id ?? null;
    setNotice(null);
    try {
      const result = await retryNotification(notificationId);
      setNotice({ severity: 'info', text: result.message });
      setFollowing(true);
      await load();
      onChangeRef.current?.();
    } catch (err) {
      setNotice({ severity: 'error', text: err.message });
    }
  };

  if (!data) {
    return error ? (
      <Alert severity="error">No se pudo cargar el estado de los emails: {error}</Alert>
    ) : (
      <LinearProgress />
    );
  }

  const total = data.pending + data.sent;
  const inProgress = following || data.sending > 0;

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={2}
          sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between' }}
        >
          <Box>
            <Typography variant="h6" component="h2">
              Emails de confirmación
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Proveedor: {data.provider}
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={<SendIcon />}
            onClick={handleSend}
            disabled={busy || data.race_past || data.pending === 0}
          >
            Enviar confirmaciones pendientes ({data.pending})
          </Button>
        </Stack>

        {data.race_past && (
          <Alert severity="info">La carrera ya se ha celebrado: no se envían confirmaciones.</Alert>
        )}
        {notice && <Alert severity={notice.severity}>{notice.text}</Alert>}
        {!notice && !following && data.last_send?.result === 'error' && (
          <Alert severity="error">
            El último envío se paró ({formatDateTime(data.last_send.finished_at)}):{' '}
            {data.last_send.summary}
          </Alert>
        )}
        {error && <Alert severity="warning">No se pudo actualizar el estado: {error}</Alert>}

        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 1 }}>
          <Chip label={`Enviadas: ${data.sent}`} color="success" variant="outlined" />
          <Chip label={`Pendientes: ${data.pending}`} variant="outlined" />
          {data.sending > 0 && <Chip label={`Enviándose: ${data.sending}`} color="info" />}
          {data.failed > 0 && <Chip label={`Fallidas: ${data.failed}`} color="error" />}
          {data.held_duplicates > 0 && (
            <Chip
              label={`Sin enviar por posible duplicado: ${data.held_duplicates}`}
              color="warning"
              variant="outlined"
            />
          )}
        </Stack>

        {inProgress && total > 0 && (
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
              Enviando… {data.sent} de {total}
            </Typography>
            <LinearProgress variant="determinate" value={(data.sent * 100) / total} />
          </Box>
        )}

        {data.failures.length > 0 && (
          <Box>
            <Typography variant="subtitle2">
              No se han podido enviar
              {data.failed > data.failures.length &&
                ` (se muestran ${data.failures.length} de ${data.failed})`}
            </Typography>
            <List dense>
              {data.failures.map((failure) => (
                <ListItem
                  key={failure.id}
                  divider
                  secondaryAction={
                    <Button
                      size="small"
                      startIcon={<ReplayIcon />}
                      onClick={() => handleRetry(failure.id)}
                    >
                      Reintentar
                    </Button>
                  }
                >
                  <ListItemText
                    sx={{ pr: 12 }}
                    primary={`Dorsal ${failure.registration.bib} · ${failure.registration.first_name} ${failure.registration.last_name} (${failure.registration.email})`}
                    secondary={`${failure.last_error} · ${failure.attempts} intentos · ${formatDateTime(failure.updated_at)}`}
                  />
                </ListItem>
              ))}
            </List>
          </Box>
        )}
      </Stack>
    </Paper>
  );
}
