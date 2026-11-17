import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from '@mui/material';
import { useState } from 'react';
import { fieldErrors } from '../api/client';
import { createRace } from '../api/races';

const EMPTY_FORM = { name: '', date: '', location: '', capacity: '' };

export default function CreateRaceDialog({ open, onClose, onCreated }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [errors, setErrors] = useState({});

  const handleChange = (event) => {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  };

  const handleClose = () => {
    setForm(EMPTY_FORM);
    setError(null);
    setErrors({});
    onClose();
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setErrors({});
    try {
      // Aforo vacío = sin límite.
      const capacity = form.capacity === '' ? null : Number(form.capacity);
      const race = await createRace({ ...form, capacity });
      setForm(EMPTY_FORM);
      onCreated(race);
    } catch (err) {
      const byField = fieldErrors(err);
      setErrors(byField);
      setError(Object.keys(byField).length ? 'Revisa los datos marcados.' : err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <form onSubmit={handleSubmit}>
        <DialogTitle>Nueva carrera</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Nombre"
              name="name"
              error={Boolean(errors.name)}
              helperText={errors.name}
              value={form.name}
              onChange={handleChange}
              required
              autoFocus
            />
            <TextField
              label="Fecha"
              name="date"
              error={Boolean(errors.date)}
              helperText={errors.date}
              type="date"
              value={form.date}
              onChange={handleChange}
              required
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              label="Lugar"
              name="location"
              error={Boolean(errors.location)}
              helperText={errors.location}
              value={form.location}
              onChange={handleChange}
            />
            <TextField
              label="Aforo"
              name="capacity"
              type="number"
              value={form.capacity}
              onChange={handleChange}
              error={Boolean(errors.capacity)}
              helperText={
                errors.capacity ||
                'Número máximo de inscripciones confirmadas. Vacío = sin límite; al llenarse, las nuevas van a lista de espera.'
              }
              slotProps={{ htmlInput: { min: 1, step: 1 } }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Cancelar</Button>
          <Button type="submit" variant="contained" disabled={saving}>
            {saving ? 'Guardando…' : 'Crear carrera'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
