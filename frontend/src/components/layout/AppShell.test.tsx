import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {render, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import {apiGet, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import {meldeDfbStatusGeaendert} from '@/lib/auth';
import {AppShell} from './AppShell';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

const SEIT = '2026-11-20T12:00:00Z';

function Ort() {
    const ort = useLocation();
    return <output data-testid="ort">{ort.pathname + ort.hash}</output>;
}

function zeige(pfad = '/dashboard', abgelehntSeit: string | null = null) {
    getRouten({
        '/api/auth/me': {user_id: 1, email: 'sr@example.org', has_dfb_credentials: true, dfb_login_abgelehnt_seit: abgelehntSeit},
    });
    return render(
        <MemoryRouter initialEntries={[pfad]}>
            <Routes>
                <Route path="*" element={(
                    <AppShell actions={<button type="button">Aktion</button>}>
                        <p>Seiteninhalt</p>
                        <Ort/>
                    </AppShell>
                )}/>
            </Routes>
        </MemoryRouter>,
    );
}

/** The red dots on the tabs - not the round icon in the notice */
const warnpunkte = (container: HTMLElement) => container.querySelectorAll('span.size-2.bg-destructive');

const kopfzeile = () => within(screen.getByRole('banner'));
const tabLeiste = () => within(screen.getByRole('navigation', {name: 'Hauptnavigation'}));

beforeEach(() => {
    apiZuruecksetzen();
    vi.stubEnv('TZ', 'Europe/Berlin');
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    document.head.innerHTML = '';
});

describe('AppShell - DFBnet-Hinweis', () => {
    it('zeigt weder Hinweis noch roten Punkt, solange DFBnet die Daten annimmt', async () => {
        const {container} = zeige('/dashboard', null);

        await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/auth/me'));
        expect(screen.getByText('Seiteninhalt')).toBeInTheDocument();
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        expect(warnpunkte(container)).toHaveLength(0);
    });

    it('zeigt Hinweis und rote Punkte an Einstellungen und "Mehr", wenn DFBnet ablehnt', async () => {
        const {container} = zeige('/dashboard', SEIT);

        expect(await screen.findByRole('alert')).toHaveTextContent('Seit dem 20.11.2026');
        // Settings sit behind "Mehr" at both widths
        expect(warnpunkte(container)).toHaveLength(2);
        expect(kopfzeile().getByRole('button', {name: /Mehr/}).querySelector('span.size-2.bg-destructive')).not.toBeNull();
        const mehr = tabLeiste().getByRole('button', {name: /Mehr/});
        expect(mehr.querySelector('span.size-2.bg-destructive')).not.toBeNull();
        expect(kopfzeile().getByRole('button', {name: 'Übersicht'}).querySelector('span.size-2')).toBeNull();
    });

    it('markiert auch im aufgeklappten "Mehr"-Menue die Einstellungen', async () => {
        const {container} = zeige('/dashboard', SEIT);
        await screen.findByRole('alert');

        await userEvent.click(tabLeiste().getByRole('button', {name: /Mehr/}));

        const menue = within(screen.getByRole('navigation', {name: 'Weitere Seiten'}));
        expect(menue.getByRole('button', {name: 'Einstellungen'}).querySelector('span.size-2.bg-destructive')).not.toBeNull();
        expect(warnpunkte(container)).toHaveLength(3);
    });

    it('steht oberhalb des Seiteninhalts', async () => {
        zeige('/spiele', SEIT);

        const hinweis = await screen.findByRole('alert');
        const inhalt = screen.getByText('Seiteninhalt');
        expect(hinweis.compareDocumentPosition(inhalt) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it('verschwindet, sobald neue Zugangsdaten gemeldet werden', async () => {
        const {container} = zeige('/settings', SEIT);
        await screen.findByRole('alert');

        getRouten({'/api/auth/me': {user_id: 1, email: 'sr@example.org', has_dfb_credentials: true, dfb_login_abgelehnt_seit: null}});
        meldeDfbStatusGeaendert();

        await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
        expect(warnpunkte(container)).toHaveLength(0);
    });

    it('zeigt keinen Hinweis, wenn /api/auth/me scheitert', async () => {
        apiGet.mockRejectedValue(new Error('500'));
        render(<MemoryRouter><AppShell><p>Inhalt</p></AppShell></MemoryRouter>);

        await waitFor(() => expect(apiGet).toHaveBeenCalled());
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
});

describe('AppShell - Navigation', () => {
    it('markiert in der Kopfzeile die aktive Seite', async () => {
        zeige('/saison');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        const aktiv = kopfzeile().getByRole('button', {name: 'Saison'});
        expect(aktiv).toHaveClass('bg-primary/10', 'text-primary');
        expect(aktiv).toHaveAttribute('aria-current', 'page');
        for (const name of ['Übersicht', 'Spiele', 'Beobachtungen', /Mehr/]) {
            expect(kopfzeile().getByRole('button', {name})).not.toHaveClass('text-primary');
        }
    });

    it('fuehrt in der Kopfzeile nur die Hauptreiter, den Rest hinter "Mehr"', async () => {
        zeige('/stammdaten');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        for (const name of ['Ligen', 'Stammdaten', 'Einstellungen', 'Fehler melden', 'Abmelden']) {
            expect(kopfzeile().queryByRole('button', {name})).not.toBeInTheDocument();
        }
        const mehr = kopfzeile().getByRole('button', {name: /Mehr/});
        expect(mehr).toHaveClass('text-primary');

        await userEvent.click(mehr);
        const menue = within(screen.getByRole('navigation', {name: 'Weitere Seiten'}));
        expect(menue.getByRole('button', {name: 'Stammdaten'})).toHaveAttribute('aria-current', 'page');
        await userEvent.click(menue.getByRole('button', {name: 'Ligen'}));
        expect(screen.getByTestId('ort')).toHaveTextContent('/ligen');
    });

    it.each([
        ['/spielbericht/7?von=saison', 'Saison'],
        ['/spielbericht/7?von=spesen', 'Spiele'],
    ])('ordnet den Spielbericht %s dem Reiter %s zu', async (pfad, reiter) => {
        zeige(pfad);
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        expect(kopfzeile().getByRole('button', {name: reiter})).toHaveAttribute('aria-current', 'page');
        expect(tabLeiste().getByRole('button', {name: reiter})).toHaveAttribute('aria-current', 'page');
        expect(tabLeiste().getByRole('button', {name: /Mehr/})).toHaveClass('text-muted-foreground');
    });

    it('markiert in der Tab-Leiste den Hauptreiter als aktuelle Seite', async () => {
        zeige('/beobachtungen');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        // On phones there is only room for the short label
        expect(tabLeiste().getByRole('button', {name: 'Noten'})).toHaveAttribute('aria-current', 'page');
        expect(tabLeiste().getByRole('button', {name: 'Noten'})).toHaveClass('text-primary');
        expect(tabLeiste().getByRole('button', {name: 'Übersicht'})).not.toHaveAttribute('aria-current');
        expect(tabLeiste().getByRole('button', {name: /Mehr/})).toHaveClass('text-muted-foreground');
    });

    it('markiert auf einer Seite hinter "Mehr" den Mehr-Knopf', async () => {
        zeige('/stammdaten');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        for (const name of ['Übersicht', 'Spiele', 'Saison', 'Noten']) {
            expect(tabLeiste().getByRole('button', {name})).not.toHaveAttribute('aria-current');
        }
        const mehr = tabLeiste().getByRole('button', {name: /Mehr/});
        expect(mehr).toHaveClass('text-primary');
        expect(mehr).toHaveAttribute('aria-expanded', 'false');

        await userEvent.click(mehr);
        const menue = within(screen.getByRole('navigation', {name: 'Weitere Seiten'}));
        expect(menue.getByRole('button', {name: 'Stammdaten'})).toHaveAttribute('aria-current', 'page');
        expect(menue.getByRole('button', {name: 'Einstellungen'})).not.toHaveAttribute('aria-current');
    });

    it('navigiert ueber Kopfzeile, Tab-Leiste und Mehr-Menue', async () => {
        zeige('/dashboard');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        await userEvent.click(kopfzeile().getByRole('button', {name: 'Spiele'}));
        expect(screen.getByTestId('ort')).toHaveTextContent('/spiele');

        await userEvent.click(tabLeiste().getByRole('button', {name: 'Saison'}));
        expect(screen.getByTestId('ort')).toHaveTextContent('/saison');

        await userEvent.click(tabLeiste().getByRole('button', {name: /Mehr/}));
        await userEvent.click(within(screen.getByRole('navigation', {name: 'Weitere Seiten'}))
            .getByRole('button', {name: 'Fehler melden'}));
        expect(screen.getByTestId('ort')).toHaveTextContent('/fehler-melden');
        // After a selection the menu closes again
        expect(screen.queryByRole('navigation', {name: 'Weitere Seiten'})).not.toBeInTheDocument();
    });

    it('schliesst das Mehr-Menue mit Escape und ueber den Hintergrund', async () => {
        zeige('/dashboard');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());
        const mehr = tabLeiste().getByRole('button', {name: /Mehr/});

        await userEvent.click(mehr);
        expect(mehr).toHaveAttribute('aria-expanded', 'true');
        await userEvent.keyboard('{Escape}');
        expect(screen.queryByRole('navigation', {name: 'Weitere Seiten'})).not.toBeInTheDocument();

        await userEvent.click(mehr);
        await userEvent.click(screen.getByRole('button', {name: 'Menü schließen'}));
        expect(screen.queryByRole('navigation', {name: 'Weitere Seiten'})).not.toBeInTheDocument();
    });

    it('zeigt die Aktionen der Seite in der Kopfzeile', async () => {
        zeige('/dashboard');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        expect(kopfzeile().getByRole('button', {name: 'Aktion'})).toBeInTheDocument();
        expect(kopfzeile().getByRole('link', {name: /Spesenfuchs/})).toHaveAttribute('href', '/dashboard');
    });

    it('meldet ueber den Abmelden-Knopf im Mehr-Menue ab', async () => {
        const ort = {href: 'http://localhost/dashboard'};
        vi.stubGlobal('location', ort);
        localStorage.setItem('token', 'jwt');
        zeige('/dashboard');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        await userEvent.click(kopfzeile().getByRole('button', {name: /Mehr/}));
        await userEvent.click(within(screen.getByRole('navigation', {name: 'Weitere Seiten'}))
            .getByRole('button', {name: 'Abmelden'}));

        expect(localStorage.getItem('token')).toBeNull();
        expect(ort.href).toBe('/login');
    });
});

describe('AppShell - Seitenkopf', () => {
    it('zeigt Ueberschrift und Beschreibung vor dem Inhalt und setzt den Tab-Titel', async () => {
        getRouten({'/api/auth/me': {user_id: 1, email: 'sr@example.org', has_dfb_credentials: true, dfb_login_abgelehnt_seit: null}});
        document.title = 'Spesenfuchs';
        const {unmount} = render(
            <MemoryRouter>
                <AppShell titel="Spiele" beschreibung="Alle Ansetzungen"><p>Seiteninhalt</p></AppShell>
            </MemoryRouter>,
        );
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        const ueberschrift = screen.getByRole('heading', {level: 1, name: 'Spiele'});
        expect(screen.getByText('Alle Ansetzungen')).toBeInTheDocument();
        expect(ueberschrift.compareDocumentPosition(screen.getByText('Seiteninhalt')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
        expect(document.title).toBe('Spiele · Spesenfuchs');

        unmount();
        expect(document.title).toBe('Spesenfuchs');
    });

    it('laesst den Kopf ohne Titel weg', async () => {
        zeige('/dashboard');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        expect(screen.queryByRole('heading', {level: 1})).not.toBeInTheDocument();
    });
});

describe('AppShell - sichere Raender', () => {
    it('setzt viewport-fit=cover und stellt den alten Wert beim Abbau wieder her', async () => {
        const meta = document.createElement('meta');
        meta.name = 'viewport';
        meta.content = 'width=device-width, initial-scale=1';
        document.head.appendChild(meta);

        const {unmount} = zeige('/dashboard');
        expect(meta.content).toBe('width=device-width, initial-scale=1, viewport-fit=cover');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        unmount();
        expect(meta.content).toBe('width=device-width, initial-scale=1');
    });

    it('haengt viewport-fit nicht doppelt an', async () => {
        const meta = document.createElement('meta');
        meta.name = 'viewport';
        meta.content = 'width=device-width, viewport-fit=cover';
        document.head.appendChild(meta);

        zeige('/dashboard');
        await waitFor(() => expect(apiGet).toHaveBeenCalled());

        expect(meta.content).toBe('width=device-width, viewport-fit=cover');
    });
});
