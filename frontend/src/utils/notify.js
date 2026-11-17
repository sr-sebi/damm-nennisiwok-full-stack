import { createContext, useContext } from 'react';

// `notify({ severity, text })` enseña un aviso breve (toast) que se cierra solo; los errores se
// quedan hasta que se cierran.
export const NotifyContext = createContext(() => {});

export const useNotify = () => useContext(NotifyContext);
