import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import {DFB_ZUGANG_ANKER, DfbLoginHinweis} from './DfbLoginHinweis';

function Ort() {
    const ort = useLocation();
    return <output data-testid="ort">{ort.pathname + ort.hash}</output>;
}

function zeige(abgelehntSeit: string, pfad = '/dashboard', inhalt: React.ReactNode = null) {
    return render(
        <MemoryRouter initialEntries={[pfad]}>
            <Routes>
                <Route path="*" element={<><DfbLoginHinweis abgelehntSeit={abgelehntSeit}/>{inhalt}<Ort/></>}/>
            </Routes>
        </MemoryRouter>,
    );
}

const scrollIntoView = vi.fn();

beforeEach(() => {
    // The date depends on the time zone; the users are in Germany
    vi.stubEnv('TZ', 'Europe/Berlin');
    scrollIntoView.mockReset();
    // jsdom does not know scrolling
    Object.defineProperty(Element.prototype, 'scrollIntoView', {configurable: true, writable: true, value: scrollIntoView});
});

afterEach(() => {
    vi.unstubAllEnvs();
    delete (Element.prototype as unknown as Record<string, unknown>).scrollIntoView;
});

describe('DfbLoginHinweis', () => {
    it('ist eine Warnung mit Titel und Knopf', () => {
        zeige('2026-11-20T12:00:00Z');

        const hinweis = screen.getByRole('alert');
        expect(hinweis).toHaveTextContent('DFBnet lehnt deine Zugangsdaten ab');
        expect(screen.getByRole('button', {name: 'Zugangsdaten erneuern'})).toBeInTheDocument();
    });

    it('nennt das Datum als TT.MM.JJJJ', () => {
        zeige('2026-11-20T12:00:00Z');

        expect(screen.getByRole('alert')).toHaveTextContent('Seit dem 20.11.2026 schlägt die Anmeldung bei DFBnet fehl.');
    });

    it('rechnet den UTC-Zeitpunkt des Servers in deutsche Zeit um', () => {
        // This is how the backend writes it: datetime.now(UTC).isoformat()
        zeige('2026-11-19T23:30:00.123456+00:00');

        expect(screen.getByRole('alert')).toHaveTextContent('Seit dem 20.11.2026 ');
    });

    it('nimmt auch einstellige Tage und Monate zweistellig', () => {
        zeige('2026-03-05T12:00:00');

        expect(screen.getByRole('alert')).toHaveTextContent('Seit dem 05.03.2026 ');
    });

    it.each(['kein Datum', ''])('faellt bei einem unbrauchbaren Datum (%j) auf "Zurzeit" zurueck', (wert) => {
        zeige(wert);

        const hinweis = screen.getByRole('alert');
        expect(hinweis).toHaveTextContent('Zurzeit schlägt die Anmeldung bei DFBnet fehl.');
        expect(hinweis).not.toHaveTextContent('Seit dem');
    });

    it('fuehrt ausserhalb der Einstellungen zur Zugangsdaten-Karte', async () => {
        zeige('2026-11-20T12:00:00Z', '/spiele');

        await userEvent.click(screen.getByRole('button', {name: 'Zugangsdaten erneuern'}));

        expect(screen.getByTestId('ort')).toHaveTextContent(`/settings#${DFB_ZUGANG_ANKER}`);
        expect(DFB_ZUGANG_ANKER).toBe('dfb-zugangsdaten');
        expect(scrollIntoView).not.toHaveBeenCalled();
    });

    it('scrollt in den Einstellungen nur zur Karte und setzt den Cursor ins erste Feld', async () => {
        zeige('2026-11-20T12:00:00Z', '/settings', (
            <div id={DFB_ZUGANG_ANKER}>
                <input aria-label="DFB-Benutzername"/>
                <input aria-label="DFB-Passwort"/>
            </div>
        ));

        await userEvent.click(screen.getByRole('button', {name: 'Zugangsdaten erneuern'}));

        expect(screen.getByTestId('ort')).toHaveTextContent(/^\/settings$/);
        expect(scrollIntoView).toHaveBeenCalledTimes(1);
        expect(scrollIntoView).toHaveBeenCalledWith({behavior: 'smooth', block: 'center'});
        expect(scrollIntoView.mock.contexts[0]).toBe(document.getElementById(DFB_ZUGANG_ANKER));
        expect(screen.getByLabelText('DFB-Benutzername')).toHaveFocus();
    });

    it('stolpert in den Einstellungen nicht, wenn die Karte fehlt', async () => {
        zeige('2026-11-20T12:00:00Z', '/settings');

        await userEvent.click(screen.getByRole('button', {name: 'Zugangsdaten erneuern'}));

        expect(screen.getByTestId('ort')).toHaveTextContent(/^\/settings$/);
        expect(scrollIntoView).not.toHaveBeenCalled();
    });
});
