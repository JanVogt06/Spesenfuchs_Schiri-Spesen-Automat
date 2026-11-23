import {beforeEach, describe, expect, it, vi} from 'vitest';
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {apiFehler, apiPost, apiZuruecksetzen} from '@/test/apiMock';
import {ChangePasswordForm} from './ChangePasswordForm';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

async function aendern(aktuell: string, neu: string, bestaetigt = neu) {
    await userEvent.type(screen.getByLabelText('Aktuelles Passwort'), aktuell);
    await userEvent.type(screen.getByLabelText('Neues Passwort'), neu);
    await userEvent.type(screen.getByLabelText('Neues Passwort bestätigen'), bestaetigt);
    await userEvent.click(screen.getByRole('button', {name: 'Passwort ändern'}));
}

beforeEach(() => {
    apiZuruecksetzen();
});

describe('ChangePasswordForm - Pruefung im Browser', () => {
    it('verlangt mindestens 8 Zeichen', async () => {
        render(<ChangePasswordForm/>);

        await aendern('altesPasswort', 'kurz12');

        expect(screen.getByText('Neues Passwort muss mindestens 8 Zeichen lang sein')).toBeInTheDocument();
        expect(apiPost).not.toHaveBeenCalled();
    });

    it('verlangt eine uebereinstimmende Bestaetigung', async () => {
        render(<ChangePasswordForm/>);

        await aendern('altesPasswort', 'neuesPasswort', 'neuesPasswurt');

        expect(screen.getByText('Die neuen Passwörter stimmen nicht überein')).toBeInTheDocument();
        expect(apiPost).not.toHaveBeenCalled();
    });

    it('verlangt ein anderes Passwort als das aktuelle', async () => {
        render(<ChangePasswordForm/>);

        await aendern('gleichesPasswort', 'gleichesPasswort');

        expect(screen.getByText('Neues Passwort muss sich vom aktuellen unterscheiden')).toBeInTheDocument();
        expect(apiPost).not.toHaveBeenCalled();
    });

    it('akzeptiert genau 8 Zeichen', async () => {
        apiPost.mockResolvedValue({data: {}});
        render(<ChangePasswordForm/>);

        await aendern('altesPasswort', '12345678');

        expect(apiPost).toHaveBeenCalled();
    });
});

describe('ChangePasswordForm - Server', () => {
    it('aendert das Passwort, meldet Erfolg und leert die Felder', async () => {
        apiPost.mockResolvedValue({data: {}});
        render(<ChangePasswordForm/>);

        await aendern('altesPasswort', 'neuesPasswort');

        expect(apiPost).toHaveBeenCalledWith('/api/auth/change-password', {
            current_password: 'altesPasswort',
            new_password: 'neuesPasswort',
        });
        expect(await screen.findByText('✓ Passwort erfolgreich geändert!')).toBeInTheDocument();
        expect(screen.getByLabelText('Aktuelles Passwort')).toHaveValue('');
        expect(screen.getByLabelText('Neues Passwort')).toHaveValue('');
        expect(screen.getByLabelText('Neues Passwort bestätigen')).toHaveValue('');
    });

    it('zeigt "Aktuelles Passwort ist falsch" aus der 400-Antwort', async () => {
        // Der Server antwortet bewusst mit 400 statt 401 - ein 401 wuerde abmelden
        apiPost.mockRejectedValue(apiFehler(400, 'Aktuelles Passwort ist falsch'));
        render(<ChangePasswordForm/>);

        await aendern('vertippt!', 'neuesPasswort');

        expect(await screen.findByText('Aktuelles Passwort ist falsch')).toBeInTheDocument();
        expect(screen.getByLabelText('Neues Passwort')).toHaveValue('neuesPasswort');
    });

    it('zeigt ein detail-Feld der Antwort', async () => {
        apiPost.mockRejectedValue(Object.assign(new Error('422'), {response: {status: 422, data: {detail: 'Feld fehlt'}}}));
        render(<ChangePasswordForm/>);

        await aendern('altesPasswort', 'neuesPasswort');

        expect(await screen.findByText('Feld fehlt')).toBeInTheDocument();
    });

    it.each([
        [401, 'Aktuelles Passwort ist falsch'],
        [400, 'Ungültige Eingabe - bitte überprüfe deine Angaben'],
        [422, 'Validierungsfehler - Passwort muss mindestens 8 Zeichen haben'],
        [500, 'Unbekannter Fehler beim Ändern des Passworts'],
    ])('faellt bei Status %i ohne Meldung auf einen eigenen Text zurueck', async (status, text) => {
        apiPost.mockRejectedValue(apiFehler(status));
        render(<ChangePasswordForm/>);

        await aendern('altesPasswort', 'neuesPasswort');

        expect(await screen.findByText(text)).toBeInTheDocument();
    });

    it('meldet einen nicht erreichbaren Server', async () => {
        apiPost.mockRejectedValue(new Error('Keine Verbindung zum Server.'));
        render(<ChangePasswordForm/>);

        await aendern('altesPasswort', 'neuesPasswort');

        expect(await screen.findByText('Server nicht erreichbar - bitte versuche es später erneut')).toBeInTheDocument();
    });

    it('sperrt den Knopf waehrend des Aenderns', async () => {
        let fertig: (wert: {data: unknown}) => void = () => {};
        apiPost.mockReturnValue(new Promise((resolve) => {
            fertig = resolve;
        }));
        render(<ChangePasswordForm/>);

        await aendern('altesPasswort', 'neuesPasswort');

        expect(screen.getByRole('button', {name: 'Wird geändert...'})).toBeDisabled();
        fertig({data: {}});
        expect(await screen.findByRole('button', {name: 'Passwort ändern'})).toBeEnabled();
    });

    it('loescht eine Fehlermeldung beim naechsten Versuch', async () => {
        apiPost.mockResolvedValue({data: {}});
        render(<ChangePasswordForm/>);
        await aendern('altesPasswort', 'kurz');
        expect(screen.getByText(/mindestens 8 Zeichen/)).toBeInTheDocument();

        await userEvent.clear(screen.getByLabelText('Neues Passwort'));
        await userEvent.clear(screen.getByLabelText('Neues Passwort bestätigen'));
        await userEvent.type(screen.getByLabelText('Neues Passwort'), 'neuesPasswort');
        await userEvent.type(screen.getByLabelText('Neues Passwort bestätigen'), 'neuesPasswort');
        await userEvent.click(screen.getByRole('button', {name: 'Passwort ändern'}));

        expect(await screen.findByText('✓ Passwort erfolgreich geändert!')).toBeInTheDocument();
        expect(screen.queryByText(/mindestens 8 Zeichen/)).not.toBeInTheDocument();
    });
});

describe('ChangePasswordForm - Anzeigen', () => {
    it('blendet aktuelles und neues Passwort getrennt ein und aus', async () => {
        render(<ChangePasswordForm/>);
        const aktuell = screen.getByLabelText('Aktuelles Passwort');
        const neu = screen.getByLabelText('Neues Passwort');
        // Die Augen-Knoepfe stehen direkt hinter ihrem Feld
        const augeAktuell = aktuell.nextElementSibling as HTMLButtonElement;
        const augeNeu = neu.nextElementSibling as HTMLButtonElement;

        expect(aktuell).toHaveAttribute('type', 'password');
        await userEvent.click(augeAktuell);
        expect(aktuell).toHaveAttribute('type', 'text');
        expect(neu).toHaveAttribute('type', 'password');

        await userEvent.click(augeNeu);
        expect(neu).toHaveAttribute('type', 'text');
        await userEvent.click(augeAktuell);
        expect(aktuell).toHaveAttribute('type', 'password');

        // Die Bestaetigung bleibt immer verdeckt
        expect(screen.getByLabelText('Neues Passwort bestätigen')).toHaveAttribute('type', 'password');
        // Die Augen sind keine Absende-Knoepfe
        expect(apiPost).not.toHaveBeenCalled();
    });
});
