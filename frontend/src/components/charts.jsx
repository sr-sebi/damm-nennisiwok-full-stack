import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { Box, Paper, Stack, Tooltip, Typography } from '@mui/material';
import { CHART } from '../utils/chartColors';
import { formatNumber } from '../utils/labels';

// Piezas de gráfico pequeñas, sin librería: indicador, barra de ocupación y lista de barras.

const share = (value, total) => (total ? Math.round((value * 100) / total) : 0);

// Un número con su etiqueta y, debajo, lo que haga falta (una barra, una nota).
export function StatTile({ label, value, hint, children }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, flex: '1 1 160px', minWidth: 0 }}>
      <Typography variant="body2" sx={{ color: CHART.secondary }}>
        {label}
      </Typography>
      <Typography component="p" sx={{ fontSize: 32, fontWeight: 600, lineHeight: 1.2, color: CHART.ink }}>
        {value}
      </Typography>
      {children}
      {hint && (
        <Typography variant="caption" sx={{ color: CHART.secondary, display: 'block', mt: 0.5 }}>
          {hint}
        </Typography>
      )}
    </Paper>
  );
}

// Ocupación frente a un límite. Por encima del límite la barra se llena en amarillo de aviso y lo
// dice con icono y texto.
export function Meter({ value, limit, label, height = 8 }) {
  if (limit == null) return null;
  const over = value > limit;
  const percent = Math.min(100, share(value, limit));
  const title = over
    ? `${formatNumber(value)} de ${formatNumber(limit)}: ${formatNumber(value - limit)} por encima`
    : `${formatNumber(value)} de ${formatNumber(limit)} (${percent} %)`;
  return (
    <Tooltip title={title}>
      <Box
        role="meter"
        aria-label={label ?? 'Ocupación'}
        aria-valuemin={0}
        aria-valuemax={limit}
        aria-valuenow={value}
        aria-valuetext={title}
        sx={{ height, borderRadius: height, bgcolor: CHART.track, overflow: 'hidden', mt: 1 }}
      >
        <Box
          sx={{
            width: `${percent}%`,
            height: '100%',
            borderRadius: height,
            bgcolor: over ? CHART.warning : CHART.data,
          }}
        />
      </Box>
    </Tooltip>
  );
}

export function OverLimit({ count, children }) {
  return (
    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', mt: 0.5 }}>
      <WarningAmberIcon sx={{ fontSize: 16, color: CHART.warning }} />
      <Typography variant="caption" sx={{ color: CHART.ink, fontWeight: 600 }}>
        {formatNumber(count)} {children}
      </Typography>
    </Stack>
  );
}

// Una barra por fila, con el nombre y la cifra en texto: se lee sin depender del color y sirve de
// tabla. Las barras comparten escala (la mayor ocupa todo el ancho).
export function BarList({ title, rows, emptyText = 'Sin datos todavía.' }) {
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  const max = Math.max(1, ...rows.map((row) => row.count));
  return (
    <Paper variant="outlined" sx={{ p: 2, flex: '1 1 280px', minWidth: 0 }}>
      <Typography variant="subtitle2" sx={{ color: CHART.ink, mb: 1 }}>
        {title}
      </Typography>
      {total === 0 ? (
        <Typography variant="body2" sx={{ color: CHART.muted }}>
          {emptyText}
        </Typography>
      ) : (
        <Box
          component="dl"
          sx={{
            m: 0,
            display: 'grid',
            gridTemplateColumns: 'minmax(80px, max-content) 1fr auto',
            columnGap: 1.5,
            rowGap: 0.75,
            alignItems: 'center',
          }}
        >
          {rows.map((row) => (
            <Box key={row.name} sx={{ display: 'contents' }}>
              <Typography component="dt" variant="body2" sx={{ color: CHART.secondary }} noWrap>
                {row.name}
              </Typography>
              <Tooltip
                title={`${row.name}: ${formatNumber(row.count)} (${share(row.count, total)} %)`}
              >
                <Box sx={{ py: 0.75 }}>
                  <Box
                    sx={{
                      height: 8,
                      width: `${(row.count * 100) / max}%`,
                      minWidth: row.count ? 4 : 0,
                      bgcolor: CHART.data,
                      borderRadius: '0 4px 4px 0',
                    }}
                  />
                </Box>
              </Tooltip>
              <Typography
                component="dd"
                variant="body2"
                sx={{ m: 0, color: CHART.ink, fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}
              >
                {formatNumber(row.count)}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Paper>
  );
}
