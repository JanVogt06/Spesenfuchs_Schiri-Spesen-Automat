import {beforeEach, describe, expect, it, vi} from 'vitest';
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {apiFehler, apiPost, apiZuruecksetzen} from '@/test/apiMock';
import {LoginForm} from './LoginForm';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

function zeige() {
    return render(
        <MemoryRouter initialEntries={['/login']}>
            <Routes>
                <Route path="/login" element={<LoginForm/>}/>
                <Route path="/dashboard" element={<p>Dashboard-Seite</p>}/>
                <Route path="/register" element={<p>Registrieren-Seite</p>}/>
            </Routes>
        </MemoryRouter>,
    );
}

async function anmelden(email = 'sr@example.org', passwort = 'geheim123') {
    await userEvent.type(screen.getByLabelText('E-Mail'), email);
    await userEvent.type(screen.getByLabelText('Passwort'), passwort);
    await userEvent.click(screen.getByRole('button', {name: 'Anmelden'}));
}

beforeEach(() => {
    apiZuruecksetzen();
});

describe('LoginForm', () => {
    it('meldet an, speichert den Token und geht zum Dashboard', async () => {
        apiPost.mockResolvedValue({data: {access_token: 'jwt', token_type: 'bearer', user_id: 1, email: 'sr@example.org'}});
        zeige();

        await anmelden();

        expect(apiPost).toHaveBeenCalledWith('/api/auth/login', {email: 'sr@example.org', password: 'geheim123'});
        expect(await screen.findByText('Dashboard-Seite')).toBeInTheDocument();
        expect(localStorage.getItem('token')).toBe('jwt');
    });

    it('zeigt die Sperrmeldung des Servers nach zu vielen Fehlversuchen', async () => {
        apiPost.mockRejectedValue(apiFehler(429, 'Zu viele Fehlversuche. Der Login ist für 15 Minuten gesperrt.'));
        zeige();

        await anmelden();

        expect(await screen.findByText('Zu viele Fehlversuche. Der Login ist für 15 Minuten gesperrt.')).toBeInTheDocument();
        expect(screen.queryByText('Dashboard-Seite')).not.toBeInTheDocument();
        expect(localStorage.getItem('token')).toBeNull();
    });

    it('zeigt die Meldung bei falschem Passwort', async () => {
        apiPost.mockRejectedValue(apiFehler(401, 'E-Mail oder Passwort falsch'));
        zeige();

        await anmelden('sr@example.org', 'falsch');

        expect(await screen.findByText('E-Mail oder Passwort falsch')).toBeInTheDocument();
        // The entries remain for the next attempt
        expect(screen.getByLabelText('E-Mail')).toHaveValue('sr@example.org');
    });

    it('zeigt ohne Verbindung die Meldung des API-Clients', async () => {
        apiPost.mockRejectedValue(new Error('Keine Verbindung zum Server. Prüfe deine Internetverbindung.'));
        zeige();

        await anmelden();

        expect(await screen.findByText(/Keine Verbindung zum Server/)).toBeInTheDocument();
    });

    it('faellt bei einer Antwort ohne Meldung auf "Login fehlgeschlagen" zurueck', async () => {
        apiPost.mockRejectedValue(Object.assign(new Error('Request failed'), {response: {status: 500, data: {}}}));
        zeige();

        await anmelden();

        expect(await screen.findByText('Login fehlgeschlagen')).toBeInTheDocument();
    });

    it('sperrt den Knopf waehrend der Anmeldung', async () => {
        let fertig: (grund: unknown) => void = () => {};
        apiPost.mockReturnValue(new Promise((_resolve, reject) => {
            fertig = reject;
        }));
        zeige();

        await anmelden();

        expect(screen.getByRole('button', {name: 'Anmelden...'})).toBeDisabled();
        fertig(apiFehler(401, 'E-Mail oder Passwort falsch'));
        expect(await screen.findByRole('button', {name: 'Anmelden'})).toBeEnabled();
    });

    it('loescht die alte Meldung beim naechsten Versuch', async () => {
        apiPost
            .mockRejectedValueOnce(apiFehler(401, 'E-Mail oder Passwort falsch'))
            .mockReturnValueOnce(new Promise(() => {}));
        zeige();

        await anmelden();
        expect(await screen.findByText('E-Mail oder Passwort falsch')).toBeInTheDocument();

        await userEvent.click(screen.getByRole('button', {name: 'Anmelden'}));
        expect(screen.queryByText('E-Mail oder Passwort falsch')).not.toBeInTheDocument();
    });

    it('verlinkt die Registrierung', async () => {
        zeige();

        await userEvent.click(screen.getByRole('link', {name: 'Jetzt registrieren'}));

        expect(screen.getByText('Registrieren-Seite')).toBeInTheDocument();
    });

    it('verlangt E-Mail und Passwort, bevor es abschickt', async () => {
        zeige();

        await userEvent.click(screen.getByRole('button', {name: 'Anmelden'}));

        expect(screen.getByLabelText('E-Mail')).toBeRequired();
        expect(screen.getByLabelText('Passwort')).toBeRequired();
        expect(apiPost).not.toHaveBeenCalled();
    });
});
