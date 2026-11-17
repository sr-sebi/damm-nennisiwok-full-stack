import UploadFileIcon from '@mui/icons-material/UploadFile';
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  FormControl,
  FormHelperText,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useEffect, useRef, useState } from 'react';
import { fieldErrors } from '../api/client';
import { listImports, uploadImport } from '../api/imports';
import { formatDateTime } from '../utils/format';
import { formatNumber, IMPORT_PHASES, isImportActive } from '../utils/labels';
import ImportProgress from './ImportProgress';
import ImportReport from './ImportReport';

const POLL_MS = 1500;
const RETRY_MS = 5000;

function UploadForm({ raceId, channels, onUploaded }) {
  const [channel, setChannel] = useState('');
  const [file, setFile] = useState(null);
  const [sending, setSending] = useState(false);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState(null);
  const inputRef = useRef(null);
  const selected = channels.find((c) => c.code === channel);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSending(true);
    setErrors({});
    setError(null);
    try {
      const batch = await uploadImport(raceId, channel, file);
      setFile(null);
      if (inputRef.current) inputRef.current.value = '';
      onUploaded(batch);
    } catch (err) {
      const byField = fieldErrors(err);
      setErrors(byField);
      if (!byField.channel && !byField.file) setError(err.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ alignItems: { sm: 'flex-start' } }}>
        <FormControl sx={{ minWidth: 220 }} size="small" error={Boolean(errors.channel)}>
          <InputLabel id="import-channel">Canal</InputLabel>
          <Select
            labelId="import-channel"
            label="Canal"
            value={channel}
            onChange={(event) => setChannel(event.target.value)}
          >
            {channels.map((c) => (
              <MenuItem key={c.code} value={c.code}>
                {c.name} (.{c.format})
              </MenuItem>
            ))}
          </Select>
          <FormHelperText>{errors.channel || 'De dónde viene el listado.'}</FormHelperText>
        </FormControl>
        <Box>
          <Button component="label" variant="outlined" startIcon={<UploadFileIcon />}>
            {file ? file.name : 'Elegir fichero'}
            <input
              ref={inputRef}
              type="file"
              hidden
              accept={selected ? `.${selected.format}` : '.xlsx,.csv'}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </Button>
          <FormHelperText error={Boolean(errors.file)}>
            {errors.file || 'Excel (.xlsx) o CSV, hasta 20 MB.'}
          </FormHelperText>
        </Box>
        <Button type="submit" variant="contained" disabled={!channel || !file || sending}>
          {sending ? 'Subiendo…' : 'Importar'}
        </Button>
      </Stack>
      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          No se pudo subir el fichero: {error}
        </Alert>
      )}
    </form>
  );
}

function statusChip(batch) {
  if (batch.status === 'hecho') return <Chip size="small" color="success" label="Terminada" />;
  if (batch.status === 'error') return <Chip size="small" color="error" label="Con error" />;
  return <Chip size="small" color="info" label={IMPORT_PHASES[batch.phase] ?? batch.phase} />;
}

function History({ imports, selectedId, onSelect }) {
  return (
    <Table size="small" aria-label="Importaciones anteriores">
      <TableHead>
        <TableRow>
          <TableCell>Fichero</TableCell>
          <TableCell>Canal</TableCell>
          <TableCell>Subida</TableCell>
          <TableCell>Estado</TableCell>
          <TableCell align="right">Altas</TableCell>
          <TableCell align="right">Ya inscritas</TableCell>
          <TableCell align="right">Rechazadas</TableCell>
          <TableCell />
        </TableRow>
      </TableHead>
      <TableBody>
        {imports.map((batch) => (
          <TableRow key={batch.id} selected={batch.id === selectedId}>
            <TableCell sx={{ wordBreak: 'break-word' }}>{batch.original_filename}</TableCell>
            <TableCell>{batch.channel?.name}</TableCell>
            <TableCell>{formatDateTime(batch.created_at)}</TableCell>
            <TableCell>{statusChip(batch)}</TableCell>
            <TableCell align="right">{formatNumber(batch.created + batch.waitlisted)}</TableCell>
            <TableCell align="right">{formatNumber(batch.already_registered)}</TableCell>
            <TableCell align="right">{formatNumber(batch.rejected)}</TableCell>
            <TableCell align="right">
              {!isImportActive(batch) && (
                <Button size="small" onClick={() => onSelect(batch.id)}>
                  Ver informe
                </Button>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// Subir un listado, seguir su progreso (y su cola) e ir a su informe al terminar.
export default function ImportPanel({ raceId, channels, onImportFinished }) {
  const [tick, setTick] = useState(0);
  const [imports, setImports] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [reportId, setReportId] = useState(null);
  const activeIds = useRef(null);
  const onFinished = useRef(onImportFinished);

  useEffect(() => {
    onFinished.current = onImportFinished;
  }, [onImportFinished]);

  // Carga el historial; mientras haya alguna en cola o en marcha, lo vuelve a pedir.
  useEffect(() => {
    let ignore = false;
    let timer;
    listImports(raceId)
      .then((data) => {
        if (ignore) return;
        setImports(data);
        setLoadError(null);
        const active = data.filter(isImportActive).map((batch) => batch.id);
        const previous = activeIds.current;
        if (previous) {
          const finished = data.filter(
            (batch) => previous.includes(batch.id) && !isImportActive(batch),
          );
          if (finished.length) {
            setReportId(finished[finished.length - 1].id);
            onFinished.current?.();
          }
        }
        activeIds.current = active;
        if (active.length) timer = setTimeout(() => setTick((t) => t + 1), POLL_MS);
      })
      .catch((err) => {
        if (ignore) return;
        setLoadError(err.message);
        if (activeIds.current?.length) timer = setTimeout(() => setTick((t) => t + 1), RETRY_MS);
      });
    return () => {
      ignore = true;
      clearTimeout(timer);
    };
  }, [raceId, tick]);

  const handleUploaded = (batch) => {
    // La nueva cuenta como activa aunque termine antes del siguiente sondeo: así se abre su informe.
    activeIds.current = [...(activeIds.current ?? []), batch.id];
    setTick((t) => t + 1);
  };

  const active = (imports ?? []).filter(isImportActive).reverse(); // la más antigua primero

  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h6" component="h2" sx={{ mb: 2 }}>
        Importar un listado
      </Typography>
      <UploadForm raceId={raceId} channels={channels} onUploaded={handleUploaded} />

      {loadError && (
        <Alert severity="warning" sx={{ mt: 2 }}>
          No se pudo cargar el estado de las importaciones: {loadError}
          {active.length > 0 && ' Se vuelve a intentar sola en unos segundos.'}
        </Alert>
      )}

      {active.length > 0 && (
        <Stack spacing={2} sx={{ mt: 3 }}>
          {active.map((batch) => (
            <ImportProgress key={batch.id} batch={batch} />
          ))}
        </Stack>
      )}

      {reportId && (
        <>
          <Divider sx={{ my: 3 }} />
          <ImportReport key={reportId} importId={reportId} onClose={() => setReportId(null)} />
        </>
      )}

      <Divider sx={{ my: 3 }} />
      <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 600, mb: 1 }}>
        Importaciones anteriores
      </Typography>
      {imports === null && !loadError && (
        <Typography color="text.secondary">Cargando las importaciones…</Typography>
      )}
      {imports !== null && imports.length === 0 && (
        <Typography color="text.secondary">
          Todavía no se ha importado ningún listado para esta carrera.
        </Typography>
      )}
      {imports !== null && imports.length > 0 && (
        <History
          imports={imports}
          selectedId={reportId}
          onSelect={setReportId}
        />
      )}
    </Paper>
  );
}
