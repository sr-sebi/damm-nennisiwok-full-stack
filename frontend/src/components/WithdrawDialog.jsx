import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Stack,
} from '@mui/material';
import { useState } from 'react';
import { withdrawRegistration } from '../api/registrations';
import { formatDate } from '../utils/format';

// Confirmación de una baja (o de la baja de quien ya no aparece en el listado de su plataforma).
export default function WithdrawDialog({ registration, onClose, onDone }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const name = `${registration.first_name} ${registration.last_name}`;
  const missing = Boolean(registration.missing_since);

  const handleConfirm = async () => {
    setSaving(true);
    setError(null);
    try {
      onDone(await withdrawRegistration(registration.id));
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>{missing ? 'Confirmar la baja' : 'Dar de baja'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          {missing && (
            <Alert severity="info">
              No aparece en el listado de {registration.channel?.name} desde el{' '}
              {formatDate(registration.missing_since)}.
            </Alert>
          )}
          <DialogContentText>
            ¿Dar de baja a <strong>{name}</strong>
            {registration.bib != null ? ` (dorsal ${registration.bib})` : ' (en lista de espera)'}?
            {registration.bib != null &&
              ' El dorsal no se vuelve a usar. Si hay lista de espera, la primera pasa a confirmada.'}{' '}
            No se puede deshacer desde la app.
          </DialogContentText>
          {error && <Alert severity="error">No se pudo dar de baja: {error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button color="error" variant="contained" onClick={handleConfirm} disabled={saving}>
          {saving ? 'Dando de baja…' : 'Dar de baja'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
