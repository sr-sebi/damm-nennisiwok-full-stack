import { Box, LinearProgress, Stack, Typography } from '@mui/material';
import { formatNumber, IMPORT_PHASES } from '../utils/labels';

function queueText(queueAhead) {
  return queueAhead
    .map((other) => {
      const state = other.status === 'procesando' ? 'en marcha' : 'en cola';
      return `«${other.original_filename}» (${other.channel}, ${state})`;
    })
    .join(', ');
}

// Una importación en cola o en marcha: fase, porcentaje y por quién espera.
export default function ImportProgress({ batch }) {
  const queued = batch.status === 'en_cola';
  const reading = batch.phase === 'leyendo';
  const rows =
    batch.total_rows != null
      ? `${formatNumber(batch.processed_rows)} de ${formatNumber(batch.total_rows)} filas`
      : null;

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline', mb: 0.5 }}>
        <Typography sx={{ fontWeight: 600 }}>{batch.original_filename}</Typography>
        <Typography variant="body2" color="text.secondary">
          {batch.channel?.name}
        </Typography>
        <Box sx={{ flex: 1 }} />
        {!queued && (
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {batch.percent} %
          </Typography>
        )}
      </Stack>
      <LinearProgress
        variant={queued || reading ? 'indeterminate' : 'determinate'}
        value={batch.percent}
        color={queued ? 'inherit' : 'primary'}
        aria-label={`Progreso de ${batch.original_filename}`}
      />
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        {IMPORT_PHASES[batch.phase] ?? batch.phase}
        {batch.phase === 'guardando' && rows && `: ${rows}`}
        {queued &&
          (batch.queue_ahead?.length
            ? `, detrás de ${queueText(batch.queue_ahead)}. Empezará sola cuando termine.`
            : ': empezará en unos segundos.')}
      </Typography>
    </Box>
  );
}
