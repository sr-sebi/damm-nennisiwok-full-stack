import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Pagination,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { listImportIssues } from '../api/imports';
import IssueList from './IssueList';

const PAGE_SIZE = 50;

// «Ver todas»: todas las incidencias de un grupo del informe, 50 por página.
export default function IssuesDialog({ importId, group, onClose }) {
  const [page, setPage] = useState(1);
  const [result, setResult] = useState({ page: null, data: null, error: null });
  const loading = result.page !== page;

  useEffect(() => {
    let ignore = false;
    listImportIssues(importId, {
      kind: group.kind,
      code: group.code,
      field: group.field,
      value: group.group_value,
      page,
    })
      .then((data) => {
        if (!ignore) setResult({ page, data, error: null });
      })
      .catch((err) => {
        if (!ignore) setResult({ page, data: null, error: err.message });
      });
    return () => {
      ignore = true;
    };
  }, [importId, group, page]);

  const pages = result.data ? Math.max(1, Math.ceil(result.data.count / PAGE_SIZE)) : 1;

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md" scroll="paper">
      <DialogTitle>{group.title}</DialogTitle>
      <DialogContent dividers>
        {loading && <LinearProgress sx={{ mb: 2 }} />}
        {result.error && (
          <Alert severity="error">No se pudieron cargar las filas: {result.error}</Alert>
        )}
        {result.data && <IssueList issues={result.data.results} />}
      </DialogContent>
      <DialogActions>
        {pages > 1 && (
          <Box sx={{ flex: 1 }}>
            <Pagination count={pages} page={page} onChange={(_, value) => setPage(value)} />
          </Box>
        )}
        <Button onClick={onClose}>Cerrar</Button>
      </DialogActions>
    </Dialog>
  );
}
