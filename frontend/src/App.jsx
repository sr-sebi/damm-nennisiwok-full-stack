import DirectionsRunIcon from '@mui/icons-material/DirectionsRun';
import SettingsIcon from '@mui/icons-material/Settings';
import { AppBar, Box, Button, Container, Toolbar, Typography } from '@mui/material';
import { Link as RouterLink, Route, Routes } from 'react-router-dom';
import NotificationsProvider from './components/NotificationsProvider';
import NotFoundPage from './pages/NotFoundPage';
import RaceDetailPage from './pages/RaceDetailPage';
import RacesPage from './pages/RacesPage';
import SettingsPage from './pages/SettingsPage';

export default function App() {
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="static" elevation={0}>
        <Toolbar>
          <DirectionsRunIcon sx={{ mr: 1 }} />
          <Typography
            variant="h6"
            component={RouterLink}
            to="/"
            sx={{ color: 'inherit', textDecoration: 'none', fontWeight: 700 }}
          >
            Dorsal
          </Typography>
          <Box sx={{ flex: 1 }} />
          <Button color="inherit" component={RouterLink} to="/configuracion" startIcon={<SettingsIcon />}>
            Configuración
          </Button>
        </Toolbar>
      </AppBar>
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <NotificationsProvider>
          <Routes>
            <Route path="/" element={<RacesPage />} />
            <Route path="/races/:raceId" element={<RaceDetailPage />} />
            <Route path="/configuracion" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </NotificationsProvider>
      </Container>
    </Box>
  );
}
