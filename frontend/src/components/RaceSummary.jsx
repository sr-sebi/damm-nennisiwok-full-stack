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
import { useState } from 'react';
import { fieldErrors } from '../api/client';
import { updateRaceCapacity } from '../api/races';
import { formatNumber } from '../utils/labels';

function Figure({ label, value, hint }) {
  return (
    <Box sx={{ minWidth: 120 }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h5" component="p" sx={{ fontWeight: 600 }}>
        {value}
      </Typography>
      {hint && (
        <Typography variant="caption" color="text.secondary">
          {hint}
        </Typography>
      )}
    </Box>
  );
}

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

export default function RaceSummary({ race, onRaceChanged, onNotice }) {
  const [editing, setEditing] = useState(false);
  const free = race.capacity == null ? null : Math.max(0, race.capacity - race.confirmed);

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

  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack direction="row" spacing={4} useFlexGap sx={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <Figure
          label="Aforo"
          value={race.capacity == null ? 'Sin límite' : formatNumber(race.capacity)}
          hint={free == null ? null : `${formatNumber(free)} plazas libres`}
        />
        <Figure label="Confirmadas" value={formatNumber(race.confirmed)} />
        <Figure label="En lista de espera" value={formatNumber(race.waitlisted)} />
        <Box sx={{ flex: 1 }} />
        <Button startIcon={<EditIcon />} onClick={() => setEditing(true)}>
          Cambiar aforo
        </Button>
      </Stack>
      {editing && (
        <CapacityDialog
          race={race}
          open
          onClose={() => setEditing(false)}
          onSaved={handleSaved}
        />
      )}
    </Paper>
  );
}
