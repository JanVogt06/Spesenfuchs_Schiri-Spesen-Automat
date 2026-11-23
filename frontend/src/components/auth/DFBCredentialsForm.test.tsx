import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {apiFehler, apiGet, apiPost, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import {DFB_STATUS_EVENT} from '@/lib/auth';
import {DFBCredentialsForm} from './DFBCredentialsForm';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

const ROT = 'DFBnet lehnt die gespeicherten Zugangsdaten ab. Trag hier dein aktuelles DFBnet-Passwort ein.';
const GRUEN = '✓ DFB-Credentials sind gespeichert';

function status(hasCredentials: boolean, abgelehntSeit: string | null = null) {
    getRouten({'/api/auth/dfb-credentials/status': {has_credentials: hasCredentials, abgelehnt_seit: abgelehntSeit}});
}

function zeige(pfad = '/settings') {
    return render(
        <MemoryRouter initialEntries={[pfad]}>
            <DFBCredentialsForm/>
        </MemoryRouter>,
    );
}

async function ausfuellenUndSpeichern(name = 'sr-muster', passwort = 'NeuesPasswort1') {
    await userEvent.type(screen.getByLabelText('DFB-Benutzername'), name);
    await userEvent.type(screen.getByLabelText('DFB-Passwort'), passwort);
    await userEvent.click(screen.getByRole('button', {name: /Speichern|Aktualisieren/}));
}

const scrollIntoView = vi.fn();
const dfbEvents = vi.fn<(e: Event) => void>();

beforeEach(() => {
    apiZuruecksetzen();
    scrollIntoView.mockReset();
    dfbEvents.mockReset();
    Object.defineProperty(Element.prototype, 'scrollIntoView', {configurable: true, writable: true, value: scrollIntoView});
    window.addEventListener(DFB_STATUS_EVENT, dfbEvents);
});

afterEach(() => {
    window.removeEventListener(DFB_STATUS_EVENT, dfbEvents);
    delete (Element.prototype as unknown as Record<string, unknown>).scrollIntoView;
});

describe('DFBCredentialsForm - Status', () => {
    it('fragt den Status unter /api/auth/dfb-credentials/status ab', async () => {
        status(false);
        zeige();

        await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/auth/dfb-credentials/status'));
    });

    it('zeigt den roten Hinweis, wenn DFBnet die gespeicherten Daten ablehnt', async () => {
        status(true, '2026-11-20T03:00:00');
        const {container} = zeige();

        expect(await screen.findByText(ROT)).toBeInTheDocument();
        expect(screen.queryByText(GRUEN)).not.toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Aktualisieren'})).toBeInTheDocument();
        expect(container.querySelector('#dfb-zugangsdaten')).toHaveClass('ring-destructive');
    });

    it('zeigt den gruenen Hinweis, wenn die Daten gespeichert und in Ordnung sind', async () => {
        status(true, null);
        const {container} = zeige();

        expect(await screen.findByText(GRUEN)).toBeInTheDocument();
        expect(screen.queryByText(ROT)).not.toBeInTheDocument();
        expect(container.querySelector('#dfb-zugangsdaten')).not.toHaveClass('ring-destructive');
    });

    it('zeigt ohne gespeicherte Daten keinen Hinweis und "Speichern"', async () => {
        status(false);
        zeige();

        await waitFor(() => expect(apiGet).toHaveBeenCalled());
        expect(screen.queryByText(ROT)).not.toBeInTheDocument();
        expect(screen.queryByText(GRUEN)).not.toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Speichern'})).toBeInTheDocument();
    });

    it('bleibt benutzbar, wenn der Status nicht geladen werden kann', async () => {
        const konsole = vi.spyOn(console, 'error').mockImplementation(() => {});
        apiGet.mockRejectedValue(new Error('500'));
        zeige();

        await waitFor(() => expect(konsole).toHaveBeenCalled());
        expect(screen.getByRole('button', {name: 'Speichern'})).toBeEnabled();
        expect(screen.queryByText(ROT)).not.toBeInTheDocument();
    });
});

describe('DFBCredentialsForm - Speichern', () => {
    it('speichert, meldet den neuen Stand und leert die Felder', async () => {
        status(false);
        apiPost.mockResolvedValue({data: {}});
        zeige();
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        await ausfuellenUndSpeichern('sr-muster', 'Geheim123');

        expect(apiPost).toHaveBeenCalledWith('/api/auth/dfb-credentials', {
            dfb_username: 'sr-muster',
            dfb_password: 'Geheim123',
        });
        expect(await screen.findByText('DFB-Credentials erfolgreich gespeichert!')).toBeInTheDocument();
        expect(dfbEvents).toHaveBeenCalledTimes(1);
        expect(screen.getByLabelText('DFB-Benutzername')).toHaveValue('');
        expect(screen.getByLabelText('DFB-Passwort')).toHaveValue('');
        expect(screen.getByText(GRUEN)).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Aktualisieren'})).toBeInTheDocument();
    });

    it('erklaert nach abgelehnten Daten, wann sich zeigt, ob die neuen passen', async () => {
        status(true, '2026-11-20T03:00:00');
        apiPost.mockResolvedValue({data: {}});
        zeige();
        await screen.findByText(ROT);

        await ausfuellenUndSpeichern();

        expect(await screen.findByText(/^Gespeichert\. Ob DFBnet sie annimmt, zeigt der nächste Abruf/)).toBeInTheDocument();
        expect(screen.queryByText(ROT)).not.toBeInTheDocument();
        expect(screen.getByText(GRUEN)).toBeInTheDocument();
        expect(dfbEvents).toHaveBeenCalledTimes(1);
    });

    it('sperrt den Knopf waehrend des Speicherns', async () => {
        status(false);
        let fertig: (wert: {data: unknown}) => void = () => {};
        apiPost.mockReturnValue(new Promise((resolve) => {
            fertig = resolve;
        }));
        zeige();
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        await ausfuellenUndSpeichern();

        expect(screen.getByRole('button', {name: 'Speichern...'})).toBeDisabled();
        fertig({data: {}});
        expect(await screen.findByRole('button', {name: 'Aktualisieren'})).toBeEnabled();
    });

    it('zeigt die Fehlermeldung des Servers und meldet nichts', async () => {
        status(true, '2026-11-20T03:00:00');
        apiPost.mockRejectedValue(apiFehler(400, 'DFB-Benutzername darf nicht leer sein'));
        zeige();
        await screen.findByText(ROT);

        await ausfuellenUndSpeichern();

        expect(await screen.findByText('DFB-Benutzername darf nicht leer sein')).toBeInTheDocument();
        expect(dfbEvents).not.toHaveBeenCalled();
        // Die Ablehnung gilt weiter, die Eingaben bleiben stehen
        expect(screen.getByText(ROT)).toBeInTheDocument();
        expect(screen.getByLabelText('DFB-Benutzername')).toHaveValue('sr-muster');
    });

    it('faellt ohne Servermeldung auf "Fehler beim Speichern" zurueck', async () => {
        status(false);
        apiPost.mockRejectedValue(new Error('Keine Verbindung zum Server.'));
        zeige();
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        await ausfuellenUndSpeichern();

        expect(await screen.findByText('Fehler beim Speichern')).toBeInTheDocument();
    });

    it('loescht eine alte Fehlermeldung beim naechsten Versuch', async () => {
        status(false);
        apiPost.mockRejectedValueOnce(apiFehler(500, 'Kaputt')).mockResolvedValueOnce({data: {}});
        zeige();
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        await ausfuellenUndSpeichern();
        expect(await screen.findByText('Kaputt')).toBeInTheDocument();

        await userEvent.click(screen.getByRole('button', {name: 'Speichern'}));
        expect(await screen.findByText('DFB-Credentials erfolgreich gespeichert!')).toBeInTheDocument();
        expect(screen.queryByText('Kaputt')).not.toBeInTheDocument();
    });
});

describe('DFBCredentialsForm - Sprung aus dem Hinweis', () => {
    it('scrollt bei #dfb-zugangsdaten zur Karte und setzt den Cursor ins erste Feld', async () => {
        status(true, '2026-11-20T03:00:00');
        const {container} = zeige('/settings#dfb-zugangsdaten');

        expect(scrollIntoView).toHaveBeenCalledWith({behavior: 'smooth', block: 'center'});
        expect(scrollIntoView.mock.contexts[0]).toBe(container.querySelector('#dfb-zugangsdaten'));
        expect(screen.getByLabelText('DFB-Benutzername')).toHaveFocus();
        await screen.findByText(ROT);
    });

    it('tut ohne Anker nichts', async () => {
        status(false);
        zeige('/settings');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        expect(scrollIntoView).not.toHaveBeenCalled();
        expect(screen.getByLabelText('DFB-Benutzername')).not.toHaveFocus();
    });
});
