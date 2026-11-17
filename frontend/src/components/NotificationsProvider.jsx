import { Alert, Snackbar } from '@mui/material';
import { useCallback, useState } from 'react';
import { NotifyContext } from '../utils/notify';

const AUTO_HIDE_MS = { success: 6000, info: 6000, warning: 9000 };

// Avisos de lo que acaba de pasar («Baja de …», «Aforo cambiado…») en un toast abajo: no se
// quedan ocupando la página. Un aviso nuevo sustituye al anterior.
export default function NotificationsProvider({ children }) {
  const [current, setCurrent] = useState(null);
  const [open, setOpen] = useState(false);

  const notify = useCallback(({ severity = 'success', text }) => {
    if (!text) return;
    setCurrent({ severity, text, key: Date.now() });
    setOpen(true);
  }, []);

  const handleClose = (_, reason) => {
    if (reason === 'clickaway') return;
    setOpen(false);
  };

  return (
    <NotifyContext.Provider value={notify}>
      {children}
      <Snackbar
        key={current?.key}
        open={open}
        onClose={handleClose}
        autoHideDuration={current ? (AUTO_HIDE_MS[current.severity] ?? null) : null}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        {current ? (
          <Alert
            severity={current.severity}
            variant="filled"
            onClose={handleClose}
            sx={{ maxWidth: 640, alignItems: 'center' }}
          >
            {current.text}
          </Alert>
        ) : undefined}
      </Snackbar>
    </NotifyContext.Provider>
  );
}
