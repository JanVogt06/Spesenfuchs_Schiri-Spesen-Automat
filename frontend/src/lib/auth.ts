import {api} from './api';

interface AuthResponse {
    access_token: string;
    token_type: string;
    user_id: number;
    email: string;
}

export interface UserInfo {
    user_id: number;
    email: string;
    has_dfb_credentials: boolean;
    /** Seit wann DFBnet die gespeicherten Zugangsdaten ablehnt (ISO, UTC) */
    dfb_login_abgelehnt_seit?: string | null;
}

/**
 * Wird ausgeloest, wenn sich der Stand der DFBnet-Zugangsdaten geaendert
 * haben kann: ein Abruf ist fertig oder neue Zugangsdaten sind gespeichert.
 * Der Hinweis in der App-Huelle laedt daraufhin neu.
 */
export const DFB_STATUS_EVENT = 'spesenfuchs:dfb-status';

export function meldeDfbStatusGeaendert() {
    window.dispatchEvent(new Event(DFB_STATUS_EVENT));
}

export async function register(email: string, password: string): Promise<AuthResponse> {
    const response = await api.post<AuthResponse>('/api/auth/register', {
        email,
        password,
    });
    localStorage.setItem('token', response.data.access_token);
    return response.data;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
    const response = await api.post<AuthResponse>('/api/auth/login', {
        email,
        password,
    });
    localStorage.setItem('token', response.data.access_token);
    return response.data;
}

export function logout() {
    localStorage.removeItem('token');
    window.location.href = '/login';
}

export async function getCurrentUser(): Promise<UserInfo> {
    const response = await api.get<UserInfo>('/api/auth/me');
    return response.data;
}

export function isAuthenticated(): boolean {
    return localStorage.getItem('token') !== null;
}
