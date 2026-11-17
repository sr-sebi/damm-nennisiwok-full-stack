import { Box, Chip, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { describeRaw, splitDifferences } from '../utils/labels';

// Filas de incidencias de una importación: línea, persona, motivo y diferencias.
export default function IssueList({ issues }) {
  const hasLines = issues.some((issue) => issue.line != null);
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          {hasLines && <TableCell sx={{ width: 70 }}>Línea</TableCell>}
          <TableCell>Persona</TableCell>
          <TableCell>Motivo</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {issues.map((issue) => {
          const differences = splitDifferences(issue.differences);
          return (
            <TableRow key={issue.id}>
              {hasLines && <TableCell>{issue.line ?? '—'}</TableCell>}
              <TableCell sx={{ wordBreak: 'break-word' }}>
                {describeRaw(issue.raw) ||
                  [issue.person, issue.bib ? `dorsal ${issue.bib}` : ''].filter(Boolean).join(', ') ||
                  '—'}
              </TableCell>
              <TableCell>
                <Stack spacing={0.5}>
                  <Box>
                    {issue.message}{' '}
                    {issue.is_new ? (
                      <Chip label="Nueva" size="small" color="info" />
                    ) : (
                      <Chip label="Ya vista" size="small" variant="outlined" />
                    )}
                  </Box>
                  {['ya_inscrita', 'repetida'].includes(issue.kind) &&
                    (differences.length ? (
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          {issue.kind === 'repetida'
                            ? 'La primera fila → esta:'
                            : 'Lo que tenemos → lo que trae este listado:'}
                        </Typography>
                        <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: 'wrap' }}>
                          {differences.map((difference) => (
                            <Chip
                              key={difference}
                              label={difference}
                              size="small"
                              color="warning"
                              variant="outlined"
                            />
                          ))}
                        </Stack>
                      </Box>
                    ) : (
                      <Typography variant="caption" color="text.secondary">
                        Mismos datos que la inscripción que ya teníamos.
                      </Typography>
                    ))}
                </Stack>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
