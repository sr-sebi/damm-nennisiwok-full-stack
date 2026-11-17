import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineOutlined';
import PeopleAltIcon from '@mui/icons-material/PeopleAlt';
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { getImport } from '../api/imports';
import { formatDateTime } from '../utils/format';
import { formatNumber } from '../utils/labels';
import IssueList from './IssueList';
import IssuesDialog from './IssuesDialog';

const COUNTERS = [
  ['created', 'altas'],
  ['waitlisted', 'en lista de espera'],
  ['updated', 'actualizadas'],
  ['unchanged', 'sin cambios'],
  ['already_registered', 'ya inscritas por otro canal'],
  ['possible_duplicates', 'posibles duplicados'],
  ['rejected', 'rechazadas'],
  ['repeated', 'repetidas en el fichero'],
  ['blank', 'filas vacías'],
  ['missing', 'no aparecen en el listado'],
];

const SECTIONS = [
  {
    kind: 'ya_inscrita',
    heading: 'Ya inscritas por otro canal',
    intro:
      'No se les ha dado otro dorsal ni se han cambiado sus datos. Si este listado trae datos distintos, habla con la persona para saber cuáles valen.',
    color: 'warning',
  },
  {
    kind: 'posible_duplicada',
    heading: 'Posibles duplicados',
    intro:
      'Mismo nombre y fecha de nacimiento que otra inscripción, con otro email. Se han inscrito aparte: revisa si son la misma persona.',
    color: 'warning',
  },
  {
    kind: 'rechazada',
    heading: 'Filas rechazadas',
    intro: 'No se han inscrito. Están agrupadas por motivo, con su línea en el fichero.',
    color: 'error',
  },
  {
    kind: 'ausente',
    heading: 'No aparecen en este listado',
    intro:
      'Siguen inscritas. Si se han dado de baja en la plataforma, confirma la baja desde la tabla de inscripciones.',
    color: 'info',
  },
];

function NewBadge({ group }) {
  if (group.new === group.count) {
    return <Chip label={group.count === 1 ? 'Nueva' : 'Todas nuevas'} size="small" color="info" />;
  }
  if (group.new === 0) {
    return (
      <Chip
        label={
          group.count === 1
            ? 'Ya salía en la importación anterior'
            : 'Ya salían en la importación anterior'
        }
        size="small"
        variant="outlined"
      />
    );
  }
  return <Chip label={`${formatNumber(group.new)} nuevas`} size="small" color="info" />;
}

function IssueGroup({ group, onShowAll }) {
  return (
    <Box sx={{ mt: 1.5 }}>
      <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography sx={{ fontWeight: 600 }}>{group.title}</Typography>
        <Chip label={formatNumber(group.count)} size="small" />
        <NewBadge group={group} />
      </Stack>
      <IssueList issues={group.examples} />
      {group.count > group.examples.length && (
        <Button size="small" onClick={() => onShowAll(group)} sx={{ mt: 0.5 }}>
          Ver las {formatNumber(group.count)}
        </Button>
      )}
    </Box>
  );
}

function Section({ section, groups, onShowAll }) {
  const total = groups.reduce((sum, group) => sum + group.count, 0);
  const highlighted = section.kind === 'ya_inscrita';
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        borderColor: `${section.color}.main`,
        borderWidth: highlighted ? 2 : 1,
        borderLeftWidth: 6,
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        {highlighted ? <PeopleAltIcon color="warning" /> : <ErrorOutlineIcon color={section.color} />}
        <Typography variant="h6" component="h3">
          {section.heading}: {formatNumber(total)}
        </Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {section.intro}
      </Typography>
      {groups.map((group) => (
        <IssueGroup
          key={`${group.kind}|${group.code}|${group.field}|${group.group_value}`}
          group={group}
          onShowAll={onShowAll}
        />
      ))}
    </Paper>
  );
}

// Informe de una importación terminada (o con error): cifras e incidencias agrupadas.
export default function ImportReport({ importId, onClose }) {
  const [result, setResult] = useState({ id: null, data: null, error: null });
  const [showAll, setShowAll] = useState(null);
  const loading = result.id !== importId;

  useEffect(() => {
    let ignore = false;
    getImport(importId)
      .then((data) => {
        if (!ignore) setResult({ id: importId, data, error: null });
      })
      .catch((err) => {
        if (!ignore) setResult({ id: importId, data: null, error: err.message });
      });
    return () => {
      ignore = true;
    };
  }, [importId]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
        <CircularProgress size={28} aria-label="Cargando el informe" />
      </Box>
    );
  }
  if (result.error) {
    return <Alert severity="error">No se pudo cargar el informe: {result.error}</Alert>;
  }

  const batch = result.data;
  const counters = COUNTERS.filter(([key]) => batch[key] > 0);
  const groups = batch.issue_groups ?? [];

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline' }}>
        <Typography variant="h6" component="h3" sx={{ flex: 1 }}>
          Informe de «{batch.original_filename}» · {batch.channel?.name}
          <Typography component="span" variant="body2" color="text.secondary">
            {' '}
            · {formatDateTime(batch.finished_at ?? batch.created_at)}
          </Typography>
        </Typography>
        {onClose && <Button onClick={onClose}>Cerrar informe</Button>}
      </Stack>

      {batch.status === 'error' && (
        <Alert severity="error">
          <AlertTitle>La importación no se ha completado</AlertTitle>
          {batch.error || 'Ha fallado por un motivo desconocido.'}
          {batch.total_rows != null &&
            ` Se guardaron ${formatNumber(batch.processed_rows)} de ${formatNumber(batch.total_rows)} filas; vuelve a importar el mismo fichero para completarla.`}
        </Alert>
      )}

      {batch.status === 'hecho' && (
        <Typography>
          {formatNumber(batch.total_rows)} filas leídas
          {counters.length > 0 && ': '}
          {counters.map(([key, label]) => `${formatNumber(batch[key])} ${label}`).join(' · ')}
          .
        </Typography>
      )}

      {batch.status === 'hecho' && groups.length === 0 && (
        <Alert severity="success">Todas las filas se han importado sin incidencias.</Alert>
      )}

      {SECTIONS.map((section) => {
        const sectionGroups = groups.filter((group) => group.kind === section.kind);
        if (sectionGroups.length === 0) return null;
        return (
          <Section
            key={section.kind}
            section={section}
            groups={sectionGroups}
            onShowAll={setShowAll}
          />
        );
      })}

      {showAll && (
        <IssuesDialog importId={importId} group={showAll} onClose={() => setShowAll(null)} />
      )}
    </Stack>
  );
}
