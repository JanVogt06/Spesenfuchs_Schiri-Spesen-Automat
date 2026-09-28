import axios from 'axios';

// Axios-Instanz mit Defaults
export const api = axios.create({
    baseURL: '',  // Leer = nutzt Vite Proxy
    headers: {
        'Content-Type': 'application/json',
    },
});

// Request-Interceptor: Fügt JWT-Token zu jedem Request hinzu
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Response-Interceptor: Behandelt Fehler global
api.interceptors.response.use(
    (response) => response,
    (error) => {
        // Ohne Antwort war der Server nicht erreichbar, meist fehlt das Netz.
        // axios meldet das nur als englisches "Network Error".
        if (!error.response && error.code !== 'ERR_CANCELED') {
            error.message = 'Keine Verbindung zum Server. Prüfe deine Internetverbindung.';
        }

        // Nur bei 401 UND wenn es NICHT der Login-Endpoint ist
        if (error.response?.status === 401) {
            const isLoginRequest = error.config?.url?.includes('/api/auth/login');
            const isRegisterRequest = error.config?.url?.includes('/api/auth/register');

            // Nur redirecten wenn es NICHT Login/Register ist
            // (Das bedeutet: Token ist abgelaufen während User eingeloggt war)
            if (!isLoginRequest && !isRegisterRequest) {
                localStorage.removeItem('token');
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
);