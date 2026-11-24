import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {render, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import {apiFehler, apiGet, apiPost, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import type {MatchData} from '@/lib/matches';
import type {SaisonDetails, SaisonSpiel} from '@/lib/saison';
import type {ScrapeRun} from '@/hooks/useScrapeRun';
import {DashboardPage} from './Dashboard';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

function Ort() {
    return <output data-testid="ort">{useLocation().pathname}</output>;
}

let naechsteId = 1;

function match(datum: string | undefined, teil: Partial<MatchData> = {}, info: MatchData['spiel_info'] = {}): MatchData {
    const id = naechsteId++;
    return {
        _id: id,
        _datum: datum,
        spiel_info: {heim_team: `Heim ${id}`, gast_team: `Gast ${id}`, spielklasse: 'Kreisliga A', mannschaftsart: 'Herren', ...info},
        schiedsrichter: [],
        spielstaette: {},
        ...teil,
    };
}

function saisonSpiel(karten: Partial<SaisonSpiel> = {}): SaisonSpiel {
    return {
        id: naechsteId++, saison: '26/27', datum: '2026-09-01', uhrzeit: '15:00', liga: 'Kreisliga A',
        heim: 'A', gast: 'B', ergebnis: '1:1',
        heim_gelb: null, heim_gelbrot: null, heim_rot: null, gast_gelb: null, gast_gelbrot: null, gast_rot: null,
        eigene_rolle: 'SR', gespann: [],
        ...karten,
    };
}

const SAISON: SaisonDetails = {
    saison: '26/27',
    spiele: [
        saisonSpiel({heim_gelb: 2, gast_gelb: 1, heim_rot: 1}),
        saisonSpiel({heim_gelb: 3, gast_gelbrot: 1}),
        saisonSpiel(),
        saisonSpiel({gast_gelb: 1}),
    ],
    einsaetze: [
        {rolle: 'SR', geleitet: '3', zurueckgegeben: '0', nicht_angetreten: '0'},
        {rolle: 'SRA 1', geleitet: '1', zurueckgegeben: '0', nicht_angetreten: '0'},
        {rolle: 'SRA 2', geleitet: '-', zurueckgegeben: '0', nicht_angetreten: '0'},
        {rolle: '4. OF', geleitet: '', zurueckgegeben: '0', nicht_angetreten: '0'},
    ],
    lehrgaenge: {lehrabend: '2', lehrabend_online: '1', leistungspruefung: '', scraped_at: ''},
};

interface Stand {
    matches?: MatchData[] | Error;
    saisons?: unknown[] | Error;
    saison?: SaisonDetails | Error;
    run?: ScrapeRun;
}

function zeige({matches = [], saisons = [{saison: '26/27'}], saison = SAISON, run = {status: 'idle', progress: null}}: Stand = {}) {
    getRouten({
        '/api/matches': matches,
        '/api/saison': saisons,
        '/api/saison/26/27': saison,
        '/api/scrape/status': run,
        '/api/auth/me': {user_id: 1, email: 'sr@example.org', has_dfb_credentials: true, dfb_login_abgelehnt_seit: null},
    });
    return render(
        <MemoryRouter initialEntries={['/dashboard']}>
            <Routes>
                <Route path="/dashboard" element={<DashboardPage/>}/>
                <Route path="*" element={<Ort/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

/** Wert und Zusatz einer Kennzahl, gefunden ueber ihre Beschriftung */
function kennzahl(label: string | RegExp) {
    const beschriftung = screen.getByText(label).closest('p')!;
    const wert = beschriftung.nextElementSibling;
    return {wert: wert?.textContent, zusatz: wert?.nextElementSibling?.textContent ?? null, karte: beschriftung};
}

async function geladen() {
    await waitFor(() => expect(screen.queryByText('Lade Übersicht...')).not.toBeInTheDocument());
}

const naechsteAnsetzungen = () => within(screen.getByText('Nächste Ansetzungen').closest('[data-slot="card"]') as HTMLElement);

beforeEach(() => {
    apiZuruecksetzen();
    naechsteId = 1;
    // Nur Date: so laufen waitFor und userEvent mit echten Timern
    vi.useFakeTimers({toFake: ['Date']});
    vi.setSystemTime(new Date(2026, 10, 23, 10, 0));
    // jsdom kennt matchMedia nicht; der Installationshinweis fragt danach
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({matches: false, media: query})));
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe('DashboardPage - Laden', () => {
    it('zeigt waehrend des Ladens einen Platzhalter', async () => {
        zeige();
        expect(screen.getByText('Lade Übersicht...')).toBeInTheDocument();
        await geladen();
    });

    it('laedt Spiele, Saisons und die neueste Saison', async () => {
        zeige({saisons: [{saison: '26/27'}, {saison: '25/26'}]});
        await geladen();

        const urls = apiGet.mock.calls.map(([url]) => url);
        expect(urls).toEqual(expect.arrayContaining(['/api/matches', '/api/saison', '/api/saison/26/27', '/api/scrape/status']));
        expect(urls).not.toContain('/api/saison/25/26');
    });

    it('zeigt die Fehlermeldung, wenn die Spiele nicht geladen werden koennen', async () => {
        zeige({matches: apiFehler(500, 'Datenbank nicht erreichbar')});

        expect(await screen.findByText('Datenbank nicht erreichbar')).toBeInTheDocument();
    });

    it('hat fuer Ladefehler ohne Meldung einen eigenen Text', async () => {
        zeige({matches: new Error('Keine Verbindung')});

        expect(await screen.findByText('Die Übersicht konnte nicht geladen werden.')).toBeInTheDocument();
    });

    it('kommt ohne Saisondaten aus', async () => {
        zeige({saisons: apiFehler(500), matches: [match('2026-11-29')]});
        await geladen();

        expect(kennzahl('Geleitete Spiele')).toMatchObject({wert: '–', zusatz: 'noch kein Abruf'});
        expect(kennzahl('Kartenschnitt')).toMatchObject({wert: '–', zusatz: 'pro Spiel, laufende Saison'});
        expect(screen.getByText('Noch keine Saisondaten abgerufen.')).toBeInTheDocument();
        expect(kennzahl('Nächstes Spiel').wert).toBe('29.11.2026');
    });

    it('kommt ohne gespeicherte Saison aus', async () => {
        zeige({saisons: []});
        await geladen();

        expect(kennzahl('Geleitete Spiele').wert).toBe('–');
        expect(apiGet.mock.calls.map(([url]) => url)).not.toContain('/api/saison/26/27');
    });

    it('kommt aus, wenn die neueste Saison nicht geladen werden kann', async () => {
        zeige({saison: apiFehler(404, 'Saison nicht gefunden')});
        await geladen();

        expect(kennzahl('Geleitete Spiele').wert).toBe('–');
        expect(screen.queryByText('Saison nicht gefunden')).not.toBeInTheDocument();
    });
});

describe('DashboardPage - Kennzahlen', () => {
    it('zeigt genau drei Kennzahlen und keine "Ohne Kilometer" mehr', async () => {
        zeige({matches: [match('2026-12-01', {_expenses: null})]});
        await geladen();

        const raster = kennzahl('Kartenschnitt').karte.closest('.grid')!;
        expect(raster.children).toHaveLength(3);
        expect(within(raster as HTMLElement).getByText('Spiele in 26/27')).toBeInTheDocument();
        expect(within(raster as HTMLElement).getByText('Nächstes Spiel')).toBeInTheDocument();
        expect(screen.queryByText(/Ohne Kilometer/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/Kilometer/i)).not.toBeInTheDocument();
    });

    it('zaehlt die Spiele der laufenden Saison', async () => {
        zeige();
        await geladen();

        expect(kennzahl('Spiele in 26/27')).toMatchObject({wert: '4', zusatz: 'laufende Saison'});
    });

    it('bildet den Kartenschnitt ueber beide Mannschaften und zaehlt Gelb-Rot und Rot als Platzverweise', async () => {
        // 9 Karten in 4 Spielen; Platzverweise: 1x Rot, 1x Gelb-Rot
        zeige();
        await geladen();

        const {wert, zusatz} = kennzahl('Kartenschnitt');
        expect(wert).toMatch(/^2[.,]3$/);
        expect(zusatz).toBe('9 Karten, davon 2 Platzverweise');
    });

    // Wie ueberall in der App mit deutschem Komma, nicht "2.3"
    it('schreibt den Kartenschnitt mit deutschem Komma', async () => {
        zeige();
        await geladen();

        expect(kennzahl('Kartenschnitt').wert).toBe('2,3');
    });

    it('zeigt ohne Spiele in der Saison keinen Schnitt', async () => {
        zeige({saison: {...SAISON, spiele: []}});
        await geladen();

        expect(kennzahl('Spiele in 26/27').wert).toBe('0');
        expect(kennzahl('Kartenschnitt').wert).toBe('–');
    });

    it('nennt das naechste Spiel mit Spielklasse', async () => {
        zeige({matches: [
            match('2026-12-06', {}, {spielklasse: 'Bezirksliga'}),
            match('2026-11-29', {}, {spielklasse: 'Landesklasse'}),
        ]});
        await geladen();

        expect(kennzahl('Nächstes Spiel')).toMatchObject({wert: '29.11.2026', zusatz: 'Landesklasse'});
    });

    it('nennt ohne Spielklasse "Ansetzung"', async () => {
        zeige({matches: [match('2026-11-29', {}, {spielklasse: ''})]});
        await geladen();

        expect(kennzahl('Nächstes Spiel').zusatz).toBe('Ansetzung');
    });
});

describe('DashboardPage - Naechste Ansetzungen', () => {
    it('zeigt nur kuenftige, noch angesetzte Spiele, sortiert und hoechstens drei', async () => {
        zeige({matches: [
            match('2026-12-13', {}, {heim_team: 'Spaet', gast_team: 'X'}),
            match('2026-11-20', {}, {heim_team: 'Vorbei', gast_team: 'X'}),
            match('2026-11-30', {}, {heim_team: 'Dritter', gast_team: 'X'}),
            match('2026-11-25', {_missing_since: '2026-11-22T03:00:00'}, {heim_team: 'Abgesetzt', gast_team: 'X'}),
            match('2026-11-29', {}, {heim_team: 'Zweiter', gast_team: 'X'}),
            match(undefined, {}, {heim_team: 'Ohne Datum', gast_team: 'X'}),
            match('2026-11-23', {}, {heim_team: 'Heute', gast_team: 'X'}),
        ]});
        await geladen();

        const titel = naechsteAnsetzungen().getAllByText(/ – X$/).map((el) => el.textContent);
        expect(titel).toEqual(['Heute – X', 'Zweiter – X', 'Dritter – X']);
        expect(screen.queryByText(/Vorbei|Abgesetzt|Ohne Datum|Spaet/)).not.toBeInTheDocument();
        expect(kennzahl('Nächstes Spiel').wert).toBe('23.11.2026');
    });

    it('sortiert Spiele am selben Tag nach der Anstosszeit', async () => {
        zeige({matches: [
            match('2026-11-29', {}, {heim_team: 'Abends', gast_team: 'X', anpfiff: 'Sonntag · 29.11.2026 · 18:30 Uhr'}),
            match('2026-11-29', {}, {heim_team: 'Morgens', gast_team: 'X', anpfiff: 'Sonntag · 29.11.2026 · 9:30 Uhr'}),
            match('2026-11-29', {}, {heim_team: 'Mittags', gast_team: 'X', anpfiff: 'Sonntag · 29.11.2026 · 13:00 Uhr'}),
        ]});
        await geladen();

        const titel = naechsteAnsetzungen().getAllByText(/ – X$/).map((el) => el.textContent);
        expect(titel).toEqual(['Morgens – X', 'Mittags – X', 'Abends – X']);
    });

    it('zeigt Datum, Spielklasse, Spielstaette und die eigene Rolle', async () => {
        zeige({matches: [match('2026-11-29', {
            spielstaette: {name: 'Sportplatz am See'},
            schiedsrichter: [{rolle: 'SR'}, {rolle: 'SRA 1', name: 'Muster, Max'}],
        }, {heim_team: 'FC Nord', gast_team: 'SV Süd', spielklasse: 'Kreisoberliga', mannschaftsart: 'Herren'})]});
        await geladen();

        const karte = naechsteAnsetzungen();
        expect(karte.getByText('FC Nord – SV Süd')).toBeInTheDocument();
        expect(karte.getByText('29.11.2026')).toBeInTheDocument();
        expect(karte.getByText('Kreisoberliga · Herren')).toBeInTheDocument();
        expect(karte.getByText('Sportplatz am See')).toBeInTheDocument();
        // Die erste Person mit Rolle UND Name
        expect(karte.getByText('SRA 1')).toBeInTheDocument();
    });

    it('nennt Spiele ohne Mannschaften "Turnier"', async () => {
        zeige({matches: [match('2026-11-29', {}, {heim_team: '', gast_team: ''})]});
        await geladen();

        expect(naechsteAnsetzungen().getByText('Turnier')).toBeInTheDocument();
    });

    it('sagt, wenn nichts ansteht', async () => {
        zeige({matches: [match('2026-11-01')]});
        await geladen();

        expect(screen.getByText('Zurzeit steht keine kommende Ansetzung in deinem DFBnet-Konto.')).toBeInTheDocument();
        expect(kennzahl('Nächstes Spiel')).toMatchObject({wert: '–', zusatz: 'keine offene Ansetzung'});
    });

    it('fuehrt ueber "Alle Spiele" zu den Spielen', async () => {
        zeige();
        await geladen();

        await userEvent.click(screen.getByRole('button', {name: 'Alle Spiele'}));

        expect(screen.getByTestId('ort')).toHaveTextContent('/spiele');
    });
});

describe('DashboardPage - Saisonkarte', () => {
    it('zeigt nur Rollen mit geleiteten Spielen und die Lehrgaenge', async () => {
        zeige();
        await geladen();

        const karte = within(screen.getByText('Saison 26/27').closest('[data-slot="card"]') as HTMLElement);
        expect(karte.getByText('SR')).toBeInTheDocument();
        expect(karte.getByText('SRA 1')).toBeInTheDocument();
        expect(karte.queryByText('SRA 2')).not.toBeInTheDocument();
        expect(karte.queryByText('4. OF')).not.toBeInTheDocument();
        expect(karte.getByText('Lehrabende').nextElementSibling).toHaveTextContent('2');
        expect(karte.getByText('Leistungsprüfung').nextElementSibling).toHaveTextContent('–');
    });

    it('laesst die Lehrgaenge weg, wenn es keine gibt', async () => {
        zeige({saison: {...SAISON, lehrgaenge: null}});
        await geladen();

        expect(screen.queryByText('Lehrabende')).not.toBeInTheDocument();
    });

    it('fuehrt ueber "Details" zur Saison', async () => {
        zeige();
        await geladen();

        await userEvent.click(screen.getByRole('button', {name: 'Details'}));

        expect(screen.getByTestId('ort')).toHaveTextContent('/saison');
    });
});

describe('DashboardPage - Abruf', () => {
    it('zeigt den Fortschritt eines laufenden Abrufs und sperrt den Knopf', async () => {
        zeige({run: {status: 'scraping', progress: {current: 1, total: 3, step: 'Lese Ansetzungen...'}}});
        await geladen();

        expect(await screen.findByText(/Lese Ansetzungen\.\.\. Die Übersicht aktualisiert sich/)).toBeInTheDocument();
        expect(screen.getByRole('button', {name: /Starte/})).toBeDisabled();
    });

    it('startet einen Abruf und zeigt dessen Fehlermeldung', async () => {
        apiPost.mockRejectedValue(apiFehler(400, 'Bitte zuerst die DFB-Zugangsdaten hinterlegen.'));
        zeige();
        await geladen();

        await userEvent.click(screen.getByRole('button', {name: /Generieren/}));

        expect(apiPost).toHaveBeenCalledWith('/api/generate', {});
        expect(await screen.findByText('Bitte zuerst die DFB-Zugangsdaten hinterlegen.')).toBeInTheDocument();
    });
});
