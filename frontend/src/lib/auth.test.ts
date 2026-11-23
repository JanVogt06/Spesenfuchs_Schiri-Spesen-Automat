import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {apiFehler, apiGet, apiPost, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import {
    DFB_STATUS_EVENT,
    getCurrentUser,
    isAuthenticated,
    login,
    logout,
    meldeDfbStatusGeaendert,
    register,
} from './auth';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

const authAntwort = {access_token: 'jwt.token', token_type: 'bearer', user_id: 1, email: 'sr@example.org'};

beforeEach(() => {
    apiZuruecksetzen();
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('login', () => {
    it('meldet an und speichert den Token', async () => {
        apiPost.mockResolvedValue({data: authAntwort});

        await expect(login('sr@example.org', 'geheim123')).resolves.toEqual(authAntwort);

        expect(apiPost).toHaveBeenCalledWith('/api/auth/login', {email: 'sr@example.org', password: 'geheim123'});
        expect(localStorage.getItem('token')).toBe('jwt.token');
        expect(isAuthenticated()).toBe(true);
    });

    it('speichert bei einem Fehler nichts', async () => {
        apiPost.mockRejectedValue(apiFehler(401, 'E-Mail oder Passwort falsch'));

        await expect(login('sr@example.org', 'falsch')).rejects.toMatchObject({response: {status: 401}});

        expect(localStorage.getItem('token')).toBeNull();
    });
});

describe('register', () => {
    it('registriert und speichert den Token', async () => {
        apiPost.mockResolvedValue({data: authAntwort});

        await register('neu@example.org', 'geheim123');

        expect(apiPost).toHaveBeenCalledWith('/api/auth/register', {email: 'neu@example.org', password: 'geheim123'});
        expect(localStorage.getItem('token')).toBe('jwt.token');
    });

    it('speichert bei einem Fehler nichts', async () => {
        apiPost.mockRejectedValue(apiFehler(400, 'E-Mail bereits registriert'));

        await expect(register('neu@example.org', 'geheim123')).rejects.toThrow();

        expect(isAuthenticated()).toBe(false);
    });
});

describe('logout', () => {
    it('loescht den Token und geht zum Login', () => {
        const ort = {href: 'http://localhost/settings'};
        vi.stubGlobal('location', ort);
        localStorage.setItem('token', 'jwt.token');

        logout();

        expect(localStorage.getItem('token')).toBeNull();
        expect(ort.href).toBe('/login');
        expect(isAuthenticated()).toBe(false);
    });
});

describe('isAuthenticated', () => {
    it('haengt nur davon ab, ob ein Token gespeichert ist', () => {
        expect(isAuthenticated()).toBe(false);
        localStorage.setItem('token', '');
        expect(isAuthenticated()).toBe(true);
    });
});

describe('getCurrentUser', () => {
    it('laedt /api/auth/me', async () => {
        const user = {user_id: 1, email: 'sr@example.org', has_dfb_credentials: true, dfb_login_abgelehnt_seit: null};
        getRouten({'/api/auth/me': user});

        await expect(getCurrentUser()).resolves.toEqual(user);
        expect(apiGet).toHaveBeenCalledWith('/api/auth/me');
    });
});

describe('meldeDfbStatusGeaendert', () => {
    it('loest DFB_STATUS_EVENT am window aus', () => {
        const hoerer = vi.fn();
        window.addEventListener(DFB_STATUS_EVENT, hoerer);

        meldeDfbStatusGeaendert();

        expect(hoerer).toHaveBeenCalledTimes(1);
        expect(hoerer.mock.calls[0][0]).toBeInstanceOf(Event);
        expect((hoerer.mock.calls[0][0] as Event).type).toBe('spesenfuchs:dfb-status');
        window.removeEventListener(DFB_STATUS_EVENT, hoerer);
    });
});
