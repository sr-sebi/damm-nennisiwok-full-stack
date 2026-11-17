import AddIcon from '@mui/icons-material/Add';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { listRaces } from '../api/races';
import CreateRaceDialog from '../components/CreateRaceDialog';
import { Meter, OverLimit, StatTile } from '../components/charts';
import { CHART } from '../utils/chartColors';
import { formatDate } from '../utils/format';
import { formatNumber } from '../utils/labels';

const isUpcoming = (race) => race.date >= new Date().toISOString().slice(0, 10);

// «47 de 45», con la barra de ocupación; sin aforo, solo las confirmadas.
function Occupancy({ race }) {
  if (race.capacity == null) {
    return (
      <Typography variant="body2">
        {formatNumber(race.confirmed)} confirmadas{' '}
        <Typography component="span" variant="body2" sx={{ color: CHART.muted }}>
          · sin aforo
        </Typography>
      </Typography>
    );
  }
  const over = race.confirmed - race.capacity;
  return (
    <Box>
      <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
        {formatNumber(race.confirmed)} de {formatNumber(race.capacity)}
      </Typography>
      <Meter value={race.confirmed} limit={race.capacity} label={`Ocupación de ${race.name}`} height={6} />
      {over > 0 && <OverLimit count={over}>por encima del aforo</OverLimit>}
    </Box>
  );
}

// Lo que hay entre todas las carreras, de un vistazo.
function RacesDashboard({ races }) {
  const upcoming = races.filter(isUpcoming);
  const sum = (list, field) => list.reduce((total, race) => total + (race[field] ?? 0), 0);
  const withCapacity = upcoming.filter((race) => race.capacity != null);
  const full = withCapacity.filter((race) => race.confirmed >= race.capacity).length;
  return (
    <Stack direction="row" useFlexGap sx={{ flexWrap: 'wrap', gap: 2, mb: 3 }}>
      <StatTile
        label="Próximas carreras"
        value={formatNumber(upcoming.length)}
        hint={`${formatNumber(races.length - upcoming.length)} ya celebradas`}
      />
      <StatTile
        label="Confirmadas en próximas carreras"
        value={formatNumber(sum(upcoming, 'confirmed'))}
        hint={`${formatNumber(sum(upcoming, 'waitlisted'))} en lista de espera`}
      />
      <StatTile
        label="Carreras con el aforo lleno"
        value={formatNumber(full)}
        hint={`de ${formatNumber(withCapacity.length)} próximas con aforo`}
      />
    </Stack>
  );
}

export default function RacesPage() {
  const navigate = useNavigate();
  const [races, setRaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  useEffect(() => {
    let ignore = false;
    listRaces()
      .then((data) => {
        if (!ignore) setRaces(data);
      })
      .catch((err) => {
        if (!ignore) setError(err.message);
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, []);

  const handleCreated = (race) => {
    setDialogOpen(false);
    navigate(`/races/${race.id}`);
  };

  return (
    <>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" sx={{ flex: 1 }}>
          Carreras
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setDialogOpen(true)}>
          Nueva carrera
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          No se pudieron cargar las carreras: {error}
        </Alert>
      )}

      {!loading && races.length > 0 && <RacesDashboard races={races} />}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table aria-label="Carreras">
            <TableHead>
              <TableRow>
                <TableCell>Carrera</TableCell>
                <TableCell>Fecha</TableCell>
                <TableCell>Lugar</TableCell>
                <TableCell sx={{ minWidth: 200 }}>Ocupación</TableCell>
                <TableCell align="right">En espera</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {races.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                    No hay carreras. Crea la primera con «Nueva carrera».
                  </TableCell>
                </TableRow>
              )}
              {races.map((race) => (
                <TableRow key={race.id} hover>
                  <TableCell>
                    <Link component={RouterLink} to={`/races/${race.id}`} underline="hover">
                      {race.name}
                    </Link>
                  </TableCell>
                  <TableCell>{formatDate(race.date)}</TableCell>
                  <TableCell>{race.location || '—'}</TableCell>
                  <TableCell>
                    <Occupancy race={race} />
                  </TableCell>
                  <TableCell align="right">{formatNumber(race.waitlisted)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <CreateRaceDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={handleCreated}
      />
    </>
  );
}
