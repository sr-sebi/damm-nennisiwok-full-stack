import { Grid, MenuItem, TextField } from '@mui/material';
import { SHIRT_SIZES } from '../utils/labels';

// Los campos de datos de una inscripción, para el alta en tienda y para corregir.
// `errors` es `{campo: 'mensaje'}` (los 400 de la API); `helpers` añade textos de ayuda.
export default function RegistrationFields({ values, errors = {}, helpers = {}, onChange, onBlur }) {
  const props = (name) => ({
    name,
    value: values[name] ?? '',
    onChange: (event) => onChange(name, event.target.value),
    onBlur: onBlur ? () => onBlur(name) : undefined,
    error: Boolean(errors[name]),
    helperText: errors[name] || helpers[name] || ' ',
    fullWidth: true,
  });

  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, sm: 6 }}>
        <TextField label="Nombre" required autoFocus {...props('first_name')} />
      </Grid>
      <Grid size={{ xs: 12, sm: 6 }}>
        <TextField label="Apellidos" required {...props('last_name')} />
      </Grid>
      <Grid size={{ xs: 12, sm: 6 }}>
        <TextField label="Email" type="email" required {...props('email')} />
      </Grid>
      <Grid size={{ xs: 12, sm: 6 }}>
        <TextField
          label="Fecha de nacimiento"
          type="date"
          required
          slotProps={{ inputLabel: { shrink: true } }}
          {...props('birth_date')}
        />
      </Grid>
      <Grid size={{ xs: 12, sm: 6 }}>
        <TextField label="Teléfono" type="tel" {...props('phone')} />
      </Grid>
      <Grid size={{ xs: 12, sm: 6 }}>
        <TextField label="Talla de camiseta" select required {...props('shirt_size')}>
          {SHIRT_SIZES.map((size) => (
            <MenuItem key={size} value={size}>
              {size}
            </MenuItem>
          ))}
        </TextField>
      </Grid>
    </Grid>
  );
}
