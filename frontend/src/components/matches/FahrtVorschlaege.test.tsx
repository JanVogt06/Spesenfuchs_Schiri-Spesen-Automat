import {beforeEach, describe, expect, it, vi} from 'vitest';
import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {apiGet, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import type {FahrtVorschlaege as Vorschlaege} from '@/lib/matches';
import {FahrtVorschlaege} from './FahrtVorschlaege';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

const VORSCHLAEGE: Vorschlaege = {
    quelle: 'strasse',
    selbst: 'sra1',
    einzeln: {km: {sr: 40, sra1: 42, sra2: 70}, gesamt: 152},
    fahrgemeinschaften: [{
        fahrten: [{fahrer: 'sr', mitfahrer: ['sra1'], km: 46}, {fahrer: 'sra2', mitfahrer: [], km: 70}],
        km: {sr: 46, sra1: 0, sra2: 70}, gesamt: 116, ersparnis: 36,
    }],
    ohne_anschrift: [],
    ohne_spielort: false,
};

function zeige(antwort: unknown = VORSCHLAEGE) {
    getRouten({'/api/matches/7/fahrten': antwort});
    const uebernehmen = vi.fn();
    render(<FahrtVorschlaege matchId={7} onUebernehmen={uebernehmen}/>);
    return uebernehmen;
}

beforeEach(() => apiZuruecksetzen());

describe('FahrtVorschlaege', () => {
    it('zeigt Einzelfahrten und Fahrgemeinschaft und uebernimmt die Kilometer', async () => {
        const uebernehmen = zeige();

        expect(await screen.findByText('SR 40 km · SRA 1 (du) 42 km · SRA 2 70 km')).toBeInTheDocument();
        expect(screen.getByText('spart 36 km')).toBeInTheDocument();
        expect(screen.getByText('SR fährt und holt SRA 1 (du) ab (46 km)')).toBeInTheDocument();
        expect(screen.getByText('SRA 2 fährt allein (70 km)')).toBeInTheDocument();

        const knoepfe = screen.getAllByRole('button', {name: 'Übernehmen'});
        await userEvent.click(knoepfe[1]);
        expect(uebernehmen).toHaveBeenCalledWith({sr: 46, sra1: 0, sra2: 70});
        await userEvent.click(knoepfe[0]);
        expect(uebernehmen).toHaveBeenLastCalledWith({sr: 40, sra1: 42, sra2: 70});
        expect(apiGet).toHaveBeenCalledWith('/api/matches/7/fahrten');
    });

    it('kennzeichnet die Luftlinie und fehlende Anschriften', async () => {
        zeige({...VORSCHLAEGE, quelle: 'luftlinie', ohne_anschrift: ['SRA 2']});

        expect(await screen.findByText(/grob über die Luftlinie geschätzt/)).toHaveTextContent('Ohne auffindbare Anschrift: SRA 2.');
    });

    it('sagt, wenn der Spielort fehlt', async () => {
        zeige({...VORSCHLAEGE, ohne_spielort: true, einzeln: {km: {}, gesamt: 0}});
        expect(await screen.findByText('Für Kilometer-Vorschläge fehlt der Ort der Spielstätte.')).toBeInTheDocument();
    });

    it('sagt, wenn die Adresssuche gestoert ist', async () => {
        zeige({...VORSCHLAEGE, quelle: 'gestoert'});
        expect(await screen.findByText(/die Adresssuche antwortet nicht/)).toBeInTheDocument();
    });

    it('zeigt ohne Fahrgemeinschaft nur die Einzelfahrten', async () => {
        zeige({...VORSCHLAEGE, fahrgemeinschaften: []});
        const liste = await screen.findByLabelText('Kilometer-Vorschläge');
        expect(within(liste).getAllByRole('button', {name: 'Übernehmen'})).toHaveLength(1);
    });
});
