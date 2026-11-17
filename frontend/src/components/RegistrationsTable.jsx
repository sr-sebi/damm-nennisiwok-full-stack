import EditIcon from '@mui/icons-material/Edit';
import PersonRemoveIcon from '@mui/icons-material/PersonRemove';
import SearchIcon from '@mui/icons-material/Search';
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  IconButton,
  InputAdornment,
  InputLabel,
  LinearProgress,
  Link,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { listRegistrations } from '../api/registrations';
import { formatDate } from '../utils/format';
import { formatNumber, REGISTRATION_STATUSES, registrationStatusLabel } from '../utils/labels';

const PAGE_SIZE = 50;
const DEBOUNCE_MS = 350;
const COLUMNS = 8;

const STATUS_COLORS = { confirmada: 'success', en_espera: 'warning', baja: 'default' };

function Marks({ registration, onSearch }) {
  const duplicate = registration.possible_duplicate_of;
  return (
    <Stack spacing={0.5} sx={{ alignItems: 'flex-start' }}>
      {duplicate && (
        <Tooltip title="Mismo nombre y fecha de nacimiento con otro email: revisa si es la misma persona.">
          <Chip
            size="small"
            color="warning"
            variant="outlined"
            label={
              <>
                Posible duplicado de{' '}
                <Link
                  component="button"
                  type="button"
                  onClick={() =>
                    onSearch(
                      duplicate.bib != null
                        ? String(duplicate.bib)
                        : `${duplicate.first_name} ${duplicate.last_name}`,
                    )
                  }
                  sx={{ verticalAlign: 'baseline', fontSize: 'inherit' }}
                >
                  {duplicate.bib != null
                    ? `dorsal ${duplicate.bib}`
                    : `${duplicate.first_name} ${duplicate.last_name}`}
                </Link>
              </>
            }
          />
        </Tooltip>
      )}
      {registration.also_channels.length > 0 && (
        <Tooltip title="Llegó también por otro canal: no se le dio otro dorsal.">
          <Chip size="small" color="info" variant="outlined" label={`También por ${registration.also_channels.join(', ')}`} />
        </Tooltip>
      )}
      {registration.missing_since && registration.status !== 'baja' && (
        <Tooltip title="Ya no aparece en el listado de su plataforma. Si se ha dado de baja allí, confirma la baja.">
          <Chip
            size="small"
            color="error"
            variant="outlined"
            label={`No aparece en el listado desde el ${formatDate(registration.missing_since)}`}
          />
        </Tooltip>
      )}
    </Stack>
  );
}

function Actions({ registration, onEdit, onWithdraw }) {
  if (registration.status === 'baja') {
    return (
      <Tooltip title="Corregir datos">
        <IconButton size="small" onClick={() => onEdit(registration)} aria-label="Corregir datos">
          <EditIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    );
  }
  return (
    <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end', alignItems: 'center' }}>
      {registration.missing_since && (
        <Button size="small" color="error" onClick={() => onWithdraw(registration)}>
          Confirmar baja
        </Button>
      )}
      <Tooltip title="Corregir datos">
        <IconButton size="small" onClick={() => onEdit(registration)} aria-label="Corregir datos">
          <EditIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      {!registration.missing_since && (
        <Tooltip title="Dar de baja">
          <IconButton size="small" onClick={() => onWithdraw(registration)} aria-label="Dar de baja">
            <PersonRemoveIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Stack>
  );
}

function EmptyRow({ search, status, total }) {
  let text = 'Esta carrera todavía no tiene inscripciones. Importa un listado o da de alta en tienda.';
  if (search) text = `Ninguna inscripción coincide con «${search}».`;
  else if (status) text = 'No hay inscripciones con este estado.';
  else if (total) text = 'No hay más inscripciones.';
  return (
    <TableRow>
      <TableCell colSpan={COLUMNS} align="center" sx={{ py: 4, color: 'text.secondary' }}>
        {text}
      </TableCell>
    </TableRow>
  );
}

// Lista paginada de inscripciones con búsqueda (por nombre, email o dorsal) y filtro de estado.
// `refreshKey` cambia cuando algo de fuera (una importación, un alta) puede haberla cambiado.
export default function RegistrationsTable({ raceId, refreshKey, onEdit, onWithdraw }) {
  const [input, setInput] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(0);
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState({ key: null, data: null, error: null });

  const key = JSON.stringify([raceId, search, status, page, refreshKey, retry]);
  const loading = result.key !== key;

  // Busca al dejar de escribir, no con cada tecla.
  useEffect(() => {
    const trimmed = input.trim();
    if (trimmed === search) return undefined;
    const timer = setTimeout(() => {
      setSearch(trimmed);
      setPage(0);
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [input, search]);

  useEffect(() => {
    let ignore = false;
    listRegistrations(raceId, { q: search, status, page: page + 1 })
      .then((data) => {
        if (!ignore) setResult({ key, data, error: null });
      })
      .catch((err) => {
        if (ignore) return;
        // Una página que ya no existe (p. ej. tras bajas): volver a la primera.
        if (err.status === 404 && page > 0) setPage(0);
        else setResult((current) => ({ key, data: current.data, error: err.message }));
      });
    return () => {
      ignore = true;
    };
  }, [key, raceId, search, status, page]);

  const showSearch = (text) => {
    setInput(text);
    setSearch(text);
    setStatus('');
    setPage(0);
  };

  const data = result.data;
  const rows = data?.results ?? [];

  return (
    <Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <TextField
          size="small"
          label="Buscar"
          placeholder="Nombre, email o dorsal"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          sx={{ flex: 1 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
          }}
        />
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id="registration-status">Estado</InputLabel>
          <Select
            labelId="registration-status"
            label="Estado"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(0);
            }}
          >
            <MenuItem value="">Todas</MenuItem>
            {REGISTRATION_STATUSES.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                {option.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Stack>

      {result.error && result.key === key && (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => setRetry((r) => r + 1)}>
              Reintentar
            </Button>
          }
        >
          No se pudieron cargar las inscripciones: {result.error}
        </Alert>
      )}

      <TableContainer component={Paper} variant="outlined">
        {loading ? <LinearProgress aria-label="Cargando inscripciones" /> : <Box sx={{ height: 4 }} />}
        <Table size="small" aria-label="Inscripciones">
          <TableHead>
            <TableRow>
              <TableCell>Dorsal</TableCell>
              <TableCell>Nombre</TableCell>
              <TableCell>Categoría</TableCell>
              <TableCell>Talla</TableCell>
              <TableCell>Canal</TableCell>
              <TableCell>Estado</TableCell>
              <TableCell>Marcas</TableCell>
              <TableCell align="right">Acciones</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!data && loading && (
              <TableRow>
                <TableCell colSpan={COLUMNS} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  Cargando inscripciones…
                </TableCell>
              </TableRow>
            )}
            {data && rows.length === 0 && !loading && (
              <EmptyRow search={search} status={status} total={data.count} />
            )}
            {rows.map((registration) => (
              <TableRow
                key={registration.id}
                hover
                sx={registration.status === 'baja' ? { opacity: 0.6 } : undefined}
              >
                <TableCell sx={{ fontWeight: 600 }}>{registration.bib ?? '—'}</TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {registration.first_name} {registration.last_name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ wordBreak: 'break-all' }}>
                    {registration.email}
                  </Typography>
                </TableCell>
                <TableCell>{registration.category}</TableCell>
                <TableCell>{registration.shirt_size || '—'}</TableCell>
                <TableCell>{registration.channel?.name}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    color={STATUS_COLORS[registration.status] ?? 'default'}
                    label={registrationStatusLabel(registration)}
                  />
                </TableCell>
                <TableCell>
                  <Marks registration={registration} onSearch={showSearch} />
                </TableCell>
                <TableCell align="right">
                  <Actions registration={registration} onEdit={onEdit} onWithdraw={onWithdraw} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {data && data.count > 0 && (
          <TablePagination
            component="div"
            count={data.count}
            page={page}
            onPageChange={(_, value) => setPage(value)}
            rowsPerPage={PAGE_SIZE}
            rowsPerPageOptions={[PAGE_SIZE]}
            labelDisplayedRows={({ from, to, count }) =>
              `${formatNumber(from)}–${formatNumber(to)} de ${formatNumber(count)}`
            }
          />
        )}
      </TableContainer>
    </Box>
  );
}
