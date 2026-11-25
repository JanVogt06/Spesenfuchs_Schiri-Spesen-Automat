import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {act, render, screen} from '@testing-library/react';
import {apiGet, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import type {Statistik} from '@/lib/statistik';
import {SpesenStatistik} from './SpesenStatistik';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

const STATISTIK: Statistik = {
    saisons: ['26/27'],
    saison: '26/27',
    quelle: 'dfbnet',
    spiele: 3,
    ohne_rolle: 1,
    ohne_satz: 0,
    ohne_ansetzung: 0,
    spesen: 80,
    fahrtkosten: {
        erfasst: 12, erfasst_spiele: 1, geschaetzt: 26.4, geschaetzt_spiele: 2, geschaetzt_km: 88,
        ohne_schaetzung: 0, luftlinie_spiele: 0, fahrgemeinschaft_spiele: 0, mitfahrer_spiele: 0,
    },
    gesamt: 118.4,
    monate: [
        {monat: '2026-09', spiele: 2, spesen: 50, fahrt_erfasst: 12, fahrt_geschaetzt: 13.2},
        {monat: '2026-10', spiele: 1, spesen: 30, fahrt_erfasst: 0, fahrt_geschaetzt: 13.2},
    ],
    rollen: [{rolle: 'SR', spiele: 2, spesen: 60}, {rolle: 'SRA 1', spiele: 1, spesen: 20}],
    offen: 0,
};

const euro = (text: string) => new RegExp(text.replace(/\s/g, '\\s'));

beforeEach(() => apiZuruecksetzen());
afterEach(() => vi.useRealTimers());

describe('SpesenStatistik', () => {
    it('zeigt Spesen, Fahrtkosten mit geschaetztem Anteil und die Monate', async () => {
        getRouten({'/api/statistik': STATISTIK});
        render(<SpesenStatistik saison="26/27"/>);

        expect(await screen.findByText(euro('80,00 €'))).toBeInTheDocument();
        expect(screen.getByText(euro('≈ 38,40 €'))).toBeInTheDocument();
        expect(screen.getByText(euro('davon 26,40 € geschätzt'))).toBeInTheDocument();
        expect(screen.getByText(euro('≈ 118,40 €'))).toBeInTheDocument();
        expect(screen.getByText(/zusammen 88 km/)).toHaveTextContent('jeweils allein');
        expect(screen.getByText(/Nicht gezählt: 1 Spiel/)).toBeInTheDocument();
        expect(screen.getByRole('table')).toBeInTheDocument();
        expect(screen.getAllByText(/Sept\. 2026/).length).toBeGreaterThan(0);
        expect(apiGet).toHaveBeenCalledWith('/api/statistik', {params: {saison: '26/27'}});
    });

    it('nennt die Quelle, Spiele ohne Ansetzung und ohne Satz', async () => {
        getRouten({'/api/statistik': {...STATISTIK, ohne_ansetzung: 19, ohne_satz: 4}});
        render(<SpesenStatistik saison="26/27"/>);

        expect(await screen.findByText(/die DFBnet als geleitet führt/)).toBeInTheDocument();
        expect(screen.getByText(/Für 19 Spiele gibt es keine/)).toBeInTheDocument();
        expect(screen.getByText(/Ohne Spesensatz: 4 Spiele/)).toBeInTheDocument();
    });

    it('sagt, wenn nur Ansetzungen gezaehlt sind', async () => {
        getRouten({'/api/statistik': {...STATISTIK, quelle: 'ansetzungen'}});
        render(<SpesenStatistik saison="26/27"/>);
        expect(await screen.findByText(/gezählt sind die Ansetzungen/)).toBeInTheDocument();
    });

    it('nennt Fahrgemeinschaften und Mitfahrten in der Schaetzung', async () => {
        getRouten({'/api/statistik': {...STATISTIK,
            fahrtkosten: {...STATISTIK.fahrtkosten, fahrgemeinschaft_spiele: 2, mitfahrer_spiele: 1}}});
        render(<SpesenStatistik saison="26/27"/>);

        expect(await screen.findByText(/2× als Fahrgemeinschaft \(davon 1× fährst du mit, 0 km\), sonst allein/))
            .toBeInTheDocument();
    });

    it('sagt "alle eingetragen", wenn nichts geschaetzt ist', async () => {
        getRouten({'/api/statistik': {
            ...STATISTIK,
            fahrtkosten: {...STATISTIK.fahrtkosten, geschaetzt: 0, geschaetzt_spiele: 0},
            monate: STATISTIK.monate.map((m) => ({...m, fahrt_geschaetzt: 0})),
        }});
        render(<SpesenStatistik saison="26/27"/>);

        expect(await screen.findByText('alle eingetragen')).toBeInTheDocument();
        expect(screen.queryByText(/≈/)).not.toBeInTheDocument();
    });

    it('sagt, wenn es fuer die Saison keine Ansetzungen gibt', async () => {
        getRouten({'/api/statistik': {...STATISTIK, saison: '26/27'}});
        render(<SpesenStatistik saison="24/25"/>);

        expect(await screen.findByText(/Für 24\/25 liegen keine vergangenen Ansetzungen/)).toBeInTheDocument();
    });

    it('fragt nach, solange Strecken offen sind', async () => {
        vi.useFakeTimers({shouldAdvanceTime: true});
        const antworten = [{...STATISTIK, offen: 4}, {...STATISTIK, offen: 0}];
        getRouten({'/api/statistik': () => antworten.shift() ?? STATISTIK});
        render(<SpesenStatistik saison="26/27"/>);

        expect(await screen.findByText('Noch 4 Strecken in Berechnung…')).toBeInTheDocument();
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1600);
        });

        expect(apiGet).toHaveBeenCalledTimes(2);
        expect(screen.queryByText(/Strecken in Berechnung/)).not.toBeInTheDocument();
    });

    it('nimmt ohne Saison die neueste und meldet jede Antwort', async () => {
        getRouten({'/api/statistik': STATISTIK});
        const geladen = vi.fn();
        render(<SpesenStatistik saison={null} onGeladen={geladen}/>);

        expect(await screen.findByText(euro('80,00 €'))).toBeInTheDocument();
        expect(apiGet).toHaveBeenCalledWith('/api/statistik', undefined);
        expect(geladen).toHaveBeenCalledWith(STATISTIK);
    });

    it('sagt ohne jede Saison, dass noch nichts vorliegt', async () => {
        getRouten({'/api/statistik': {...STATISTIK, saisons: [], saison: null, spiele: 0, ohne_rolle: 0, monate: []}});
        render(<SpesenStatistik saison={null}/>);
        expect(await screen.findByText(/Noch liegen keine vergangenen/)).toBeInTheDocument();
    });

    it('meldet einen Ladefehler', async () => {
        getRouten({'/api/statistik': new Error('500')});
        render(<SpesenStatistik saison="26/27"/>);
        expect(await screen.findByText('Die Statistik konnte nicht geladen werden.')).toBeInTheDocument();
    });
});
