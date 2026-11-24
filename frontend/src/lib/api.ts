import axios from 'axios';

// Axios instance with defaults
export const api = axios.create({
    baseURL: '',  // Empty = uses the Vite proxy
    headers: {
        'Content-Type': 'application/json',
    },
});

// Request interceptor: adds the JWT token to every request
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Response interceptor: handles errors globally
api.interceptors.response.use(
    (response) => response,
    (error) => {
        // Without a response the server was unreachable, usually the network is missing.
        // axios only reports this as an English "Network Error".
        if (!error.response && error.code !== 'ERR_CANCELED') {
            error.message = 'Keine Verbindung zum Server. Prüfe deine Internetverbindung.';
        }

        // Only on 401 AND if it is NOT the login endpoint
        if (error.response?.status === 401) {
            const isLoginRequest = error.config?.url?.includes('/api/auth/login');
            const isRegisterRequest = error.config?.url?.includes('/api/auth/register');

            // Only redirect if it is NOT login/register
            // (This means: token expired while the user was logged in)
            if (!isLoginRequest && !isRegisterRequest) {
                localStorage.removeItem('token');
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
);