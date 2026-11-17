import EditIcon from '@mui/icons-material/Edit';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { fieldErrors } from '../api/client';
import { getRaceStats, updateRaceCapacity } from '../api/races';
import { formatNumber } from '../utils/labels';
import { BarList, Meter, OverLimit, StatTile } from './charts';

function CapacityDialog({ race, open, onClose, onSaved }) {
  const [value, setValue] = useState(race.capacity ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const result = await updateRaceCapacity(race.id, value === '' ? null : Number(value));
      onSaved(result);
    } catch (err) {
      setError(fieldErrors(err).capacity || err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <form onSubmit={handleSubmit}>
        <DialogTitle>Cambiar el aforo</DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            <DialogContentText>
              Si lo subes, las primeras de la lista de espera pasan a confirmadas con un dorsal
              nuevo. Si lo bajas, nadie pierde su plaza: solo las nuevas irán a lista de espera.
            </DialogContentText>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Aforo"
              type="number"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              helperText="Vacío = sin límite."
              autoFocus
              slotProps={{ htmlInput: { min: 1, step: 1 } }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancelar</Button>
          <Button type="submit" variant="contained" disabled={saving}>
            {saving ? 'Guardando…' : 'Guardar aforo'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

function useStats(raceId, refreshKey) {
  const [result, setResult] = useState({ key: null, data: null, error: null });
  const key = `${raceId}-${refreshKey}`;
  useEffect(() => {
    let ignore = false;
    getRaceStats(raceId)
      .then((data) => {
        if (!ignore) setResult({ key, data, error: null });
      })
      .catch((err) => {
        if (!ignore) setResult((current) => ({ ...current, key, error: err.message }));
      });
    return () => {
      ignore = true;
    };
  }, [raceId, key]);
  return result;
}

// Resumen de la carrera: plazas, estados, categorías, canales y emails.
export default function RaceSummary({ race, refreshKey, onRaceChanged, onNotice }) {
  const [editing, setEditing] = useState(false);
  const { data: stats, error } = useStats(race.id, refreshKey);

  const handleSaved = (result) => {
    setEditing(false);
    const { promoted, message, ...updated } = result;
    onRaceChanged(updated);
    const capacityText =
      updated.capacity == null ? 'sin límite' : formatNumber(updated.capacity);
    onNotice({
      severity: 'success',
      text: `Aforo cambiado a ${capacityText}. ${
        promoted.length ? message : 'Nadie sale de la lista de espera.'
      }`,
    });
  };

  const confirmed = stats?.confirmed ?? race.confirmed;
  const capacity = race.capacity;
  const over = capacity != null && confirmed > capacity ? confirmed - capacity : 0;
  const free = capacity == null ? null : Math.max(0, capacity - confirmed);
  const emails = stats?.emails;

  return (
    <Stack spacing={2}>
      <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 2 }}>
        <StatTile
          label={capacity == null ? 'Confirmadas (sin aforo)' : `Confirmadas · aforo ${formatNumber(capacity)}`}
          value={formatNumber(confirmed)}
          hint={over ? null : free == null ? 'Sin límite de plazas.' : `${formatNumber(free)} plazas libres`}
        >
          <Meter value={confirmed} limit={capacity} label="Confirmadas frente al aforo" />
          {over > 0 && <OverLimit count={over}>por encima del aforo: las bajas no sacan a nadie de la espera hasta bajar de él</OverLimit>}
          <Button size="small" startIcon={<EditIcon />} onClick={() => setEditing(true)} sx={{ mt: 1, ml: -1 }}>
            Cambiar aforo
          </Button>
        </StatTile>
        <StatTile
          label="En lista de espera"
          value={formatNumber(stats?.waitlisted ?? race.waitlisted)}
          hint={capacity == null ? 'Sin aforo no hay lista de espera.' : 'Entran por orden al quedar plazas.'}
        />
        <StatTile label="Bajas" value={stats ? formatNumber(stats.withdrawn) : '—'} hint="El dorsal no se reutiliza." />
        <StatTile
          label="Emails de confirmación enviados"
          value={emails ? formatNumber(emails.sent) : '—'}
          hint={emails?.failed ? `${formatNumber(emails.failed)} fallidos` : `de ${formatNumber(confirmed)} confirmadas`}
        />
      </Stack>
      {stats && (stats.possible_duplicates > 0 || stats.missing > 0) && (
        <Stack direction="row" spacing={3} useFlexGap sx={{ flexWrap: 'wrap' }}>
          {stats.possible_duplicates > 0 && (
            <OverLimit count={stats.possible_duplicates}>posibles duplicados por revisar</OverLimit>
          )}
          {stats.missing > 0 && (
            <OverLimit count={stats.missing}>no aparecen en el listado de su plataforma</OverLimit>
          )}
        </Stack>
      )}
      {error && !stats && (
        <Alert severity="warning">No se pudieron cargar las cifras de la carrera: {error}</Alert>
      )}
      {stats && (
        <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 2 }}>
          <BarList title="Inscritas por categoría (confirmadas y en espera)" rows={stats.by_category} />
          <BarList title="Inscritas por canal (confirmadas y en espera)" rows={stats.by_channel} />
        </Stack>
      )}
      {editing && (
        <CapacityDialog
          race={race}
          open
          onClose={() => setEditing(false)}
          onSaved={handleSaved}
        />
      )}
    </Stack>
  );
}
