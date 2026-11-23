import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {AxiosError, CanceledError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig} from 'axios';
import {api} from './api';

/** Antwort, wie ein echter Adapter sie liefern wuerde */
function antwort(config: InternalAxiosRequestConfig, status: number, data: unknown = {}): AxiosResponse {
    return {data, status, statusText: '', headers: {}, config};
}

/** Adapter, der mit dem Status scheitert - wie axios' settle() bei 4xx/5xx */
function scheitertMit(status: number, data: unknown = {}): AxiosAdapter {
    return (config) => Promise.reject(
        new AxiosError(`Request failed with status code ${status}`, 'ERR_BAD_REQUEST', config, null, antwort(config, status, data)),
    );
}

const originalAdapter = api.defaults.adapter;
let ort: {href: string};

beforeEach(() => {
    ort = {href: 'http://localhost/dashboard'};
    vi.stubGlobal('location', ort);
});

afterEach(() => {
    api.defaults.adapter = originalAdapter;
    vi.unstubAllGlobals();
});

describe('Request-Interceptor', () => {
    it('setzt den Bearer-Token aus dem localStorage', async () => {
        localStorage.setItem('token', 'abc.def');
        const adapter = vi.fn<AxiosAdapter>(async (config) => antwort(config, 200));
        api.defaults.adapter = adapter;

        await api.get('/api/matches');

        const config = adapter.mock.calls[0][0];
        expect(config.headers.Authorization).toBe('Bearer abc.def');
    });

    it('laesst den Header ohne Token weg', async () => {
        const adapter = vi.fn<AxiosAdapter>(async (config) => antwort(config, 200));
        api.defaults.adapter = adapter;

        await api.get('/api/matches');

        expect(adapter.mock.calls[0][0].headers.Authorization).toBeUndefined();
    });

    it('schickt JSON als Content-Type', async () => {
        const adapter = vi.fn<AxiosAdapter>(async (config) => antwort(config, 200));
        api.defaults.adapter = adapter;

        await api.post('/api/generate', {});

        expect(String(adapter.mock.calls[0][0].headers['Content-Type'])).toContain('application/json');
    });

    it('reicht erfolgreiche Antworten unveraendert durch', async () => {
        api.defaults.adapter = async (config) => antwort(config, 200, {ok: true});

        const response = await api.get('/api/matches');

        expect(response.data).toEqual({ok: true});
    });
});

describe('Response-Interceptor bei 401', () => {
    it('loescht bei einem normalen Endpunkt den Token und leitet zum Login', async () => {
        localStorage.setItem('token', 'abgelaufen');
        api.defaults.adapter = scheitertMit(401);

        await expect(api.get('/api/matches')).rejects.toMatchObject({response: {status: 401}});

        expect(localStorage.getItem('token')).toBeNull();
        expect(ort.href).toBe('/login');
    });

    it.each(['/api/auth/login', '/api/auth/register'])('leitet bei %s nicht um', async (url) => {
        localStorage.setItem('token', 'bleibt');
        api.defaults.adapter = scheitertMit(401, {error: {message: 'E-Mail oder Passwort falsch'}});

        await expect(api.post(url, {})).rejects.toMatchObject({
            response: {status: 401, data: {error: {message: 'E-Mail oder Passwort falsch'}}},
        });

        expect(localStorage.getItem('token')).toBe('bleibt');
        expect(ort.href).toBe('http://localhost/dashboard');
    });

    it('meldet bei anderen Fehlern nicht ab', async () => {
        localStorage.setItem('token', 'bleibt');
        api.defaults.adapter = scheitertMit(400, {error: {message: 'Aktuelles Passwort ist falsch'}});

        await expect(api.post('/api/auth/change-password', {})).rejects.toMatchObject({response: {status: 400}});

        expect(localStorage.getItem('token')).toBe('bleibt');
        expect(ort.href).toBe('http://localhost/dashboard');
    });

    it('laesst die Fehlermeldung einer Serverantwort stehen', async () => {
        api.defaults.adapter = scheitertMit(500);

        await expect(api.get('/api/matches')).rejects.toThrow('Request failed with status code 500');
    });
});

describe('Response-Interceptor ohne Antwort', () => {
    it('ersetzt "Network Error" durch eine deutsche Meldung', async () => {
        api.defaults.adapter = (config) => Promise.reject(new AxiosError('Network Error', 'ERR_NETWORK', config));

        await expect(api.get('/api/matches')).rejects.toThrow(
            'Keine Verbindung zum Server. Prüfe deine Internetverbindung.',
        );
        expect(ort.href).toBe('http://localhost/dashboard');
    });

    it('laesst abgebrochene Anfragen unangetastet', async () => {
        api.defaults.adapter = (config) => Promise.reject(new CanceledError(undefined, config));

        const fehler = await api.get('/api/matches').catch((e: unknown) => e);

        expect(fehler).toBeInstanceOf(CanceledError);
        expect((fehler as CanceledError<unknown>).code).toBe('ERR_CANCELED');
        expect((fehler as CanceledError<unknown>).message).toBe('canceled');
    });
});
