import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { getRace, listChannels } from '../api/races';
import { clearPossibleDuplicate } from '../api/registrations';
import ConfirmationsPanel from '../components/ConfirmationsPanel';
import EditRegistrationDialog from '../components/EditRegistrationDialog';
import ImportPanel from '../components/ImportPanel';
import RaceSummary from '../components/RaceSummary';
import RegistrationForm from '../components/RegistrationForm';
import RegistrationsTable from '../components/RegistrationsTable';
import WithdrawDialog from '../components/WithdrawDialog';
import { formatDate } from '../utils/format';

function useRace(raceId, version) {
  const [result, setResult] = useState({ id: null, data: null, error: null });

  useEffect(() => {
    let ignore = false;
    getRace(raceId)
      .then((data) => {
        if (!ignore) setResult({ id: raceId, data, error: null });
      })
      .catch((err) => {
        if (!ignore) setResult((current) => ({ ...current, id: raceId, error: err }));
      });
    return () => {
      ignore = true;
    };
  }, [raceId, version]);

  const current = result.id === raceId ? result : { data: null, error: null };
  const replace = useCallback((data) => setResult({ id: raceId, data, error: null }), [raceId]);
  return { race: current.data, error: current.error, loading: result.id !== raceId, replace };
}

function useChannels() {
  const [channels, setChannels] = useState({ data: [], error: null });
  useEffect(() => {
    let ignore = false;
    listChannels()
      .then((data) => {
        if (!ignore) setChannels({ data, error: null });
      })
      .catch((err) => {
        if (!ignore) setChannels({ data: [], error: err.message });
      });
    return () => {
      ignore = true;
    };
  }, []);
  return channels;
}

export default function RaceDetailPage() {
  const { raceId } = useParams();
  // Sube cuando algo cambia las inscripciones: recarga las cifras de la carrera y la tabla.
  const [version, setVersion] = useState(0);
  const { race, error, loading, replace } = useRace(raceId, version);
  const channels = useChannels();
  const [notice, setNotice] = useState(null);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [withdrawing, setWithdrawing] = useState(null);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  const shopChannel = channels.data.find((channel) => channel.kind === 'presencial');

  if (loading && !race) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress aria-label="Cargando la carrera" />
      </Box>
    );
  }

  if (!race) {
    return (
      <Stack spacing={2}>
        <Alert severity="error">
          {error?.status === 404
            ? 'Esta carrera no existe o se ha borrado.'
            : `No se pudo cargar la carrera: ${error?.message}`}
        </Alert>
        <Box>
          <Button component={RouterLink} to="/" startIcon={<ArrowBackIcon />}>
            Volver a las carreras
          </Button>
        </Box>
      </Stack>
    );
  }

  const handleCreated = (result) => {
    setCreating(false);
    setNotice({
      severity: result.outcome === 'en_espera' ? 'warning' : 'success',
      text: [result.message, result.possible_duplicate].filter(Boolean).join(' '),
    });
    refresh();
  };

  // Al cambiar el aforo: cifras nuevas ya, y la tabla otra vez (puede haber salido gente de la espera).
  const handleRaceChanged = (data) => {
    replace(data);
    refresh();
  };

  const handleEditExisting = (registrationId) => {
    setCreating(false);
    setEditingId(registrationId);
  };

  const handleNotDuplicate = async (registration) => {
    try {
      const result = await clearPossibleDuplicate(registration.id);
      setNotice({ severity: 'success', text: result.message });
      refresh();
    } catch (err) {
      setNotice({ severity: 'error', text: `No se pudo quitar la marca: ${err.message}` });
    }
  };

  const handleWithdrawn = (result) => {
    setWithdrawing(null);
    setNotice({ severity: result.already_withdrawn ? 'info' : 'success', text: result.message });
    refresh();
  };

  return (
    <Stack spacing={3}>
      <Box>
        <Button component={RouterLink} to="/" startIcon={<ArrowBackIcon />} sx={{ mb: 1 }}>
          Carreras
        </Button>
        <Typography variant="h4" component="h1">
          {race.name}
        </Typography>
        <Typography color="text.secondary">
          {formatDate(race.date)}
          {race.location && ` · ${race.location}`}
        </Typography>
      </Box>

      <RaceSummary race={race} onRaceChanged={handleRaceChanged} onNotice={setNotice} />

      {channels.error && (
        <Alert severity="error">
          No se pudieron cargar los canales, así que no se puede importar ni dar de alta:{' '}
          {channels.error}
        </Alert>
      )}

      <ImportPanel raceId={race.id} channels={channels.data} onImportFinished={refresh} />

      <ConfirmationsPanel key={`${race.id}-${version}`} raceId={race.id} onChange={refresh} />

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack direction="row" sx={{ alignItems: 'center', mb: 2 }}>
          <Typography variant="h6" component="h2" sx={{ flex: 1 }}>
            Inscripciones
          </Typography>
          <Tooltip title={shopChannel ? '' : 'No hay ningún canal presencial configurado.'}>
            <span>
              <Button
                variant="contained"
                startIcon={<PersonAddIcon />}
                onClick={() => setCreating(true)}
                disabled={!shopChannel}
              >
                Alta en {shopChannel ? shopChannel.name.toLowerCase() : 'tienda'}
              </Button>
            </span>
          </Tooltip>
        </Stack>
        {notice && (
          <Alert severity={notice.severity} onClose={() => setNotice(null)} sx={{ mb: 2 }}>
            {notice.text}
          </Alert>
        )}
        <RegistrationsTable
          raceId={race.id}
          refreshKey={version}
          onEdit={(registration) => setEditingId(registration.id)}
          onWithdraw={setWithdrawing}
          onNotDuplicate={handleNotDuplicate}
        />
      </Paper>

      {creating && shopChannel && (
        <RegistrationForm
          raceId={race.id}
          channel={shopChannel}
          onClose={() => setCreating(false)}
          onCreated={handleCreated}
          onEditExisting={handleEditExisting}
        />
      )}
      {editingId && (
        <EditRegistrationDialog
          key={editingId}
          registrationId={editingId}
          onClose={() => setEditingId(null)}
          onSaved={refresh}
        />
      )}
      {withdrawing && (
        <WithdrawDialog
          registration={withdrawing}
          onClose={() => setWithdrawing(null)}
          onDone={handleWithdrawn}
        />
      )}
    </Stack>
  );
}
