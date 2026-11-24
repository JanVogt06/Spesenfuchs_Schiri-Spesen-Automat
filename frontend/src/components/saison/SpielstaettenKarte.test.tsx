import {beforeEach, describe, expect, it, vi} from 'vitest';
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {apiZuruecksetzen, getRouten} from '@/test/apiMock';
import type {Spielstaetten} from '@/lib/spielstaetten';
import {SpielstaettenKarte} from './SpielstaettenKarte';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);
vi.mock('@/components/ThemeProvider', () => ({useTheme: () => ({resolvedTheme: 'light'})}));

const marker = vi.hoisted(() => [] as {punkt: number[]; optionen: Record<string, unknown>}[]);
vi.mock('leaflet', () => {
    const kette = () => {
        const objekt: Record<string, unknown> = {};
        for (const name of ['addTo', 'bindTooltip', 'bindPopup']) objekt[name] = () => objekt;
        return objekt;
    };
    const L = {
        map: () => ({fitBounds: vi.fn(), invalidateSize: vi.fn(), remove: vi.fn()}),
        tileLayer: () => kette(),
        circleMarker: (punkt: number[], optionen: Record<string, unknown>) => {
            marker.push({punkt, optionen});
            return kette();
        },
        latLngBounds: (punkte: unknown) => punkte,
    };
    return {default: L};
});

/** Die Zeile "2 Spielstätten · 3 Einsätze" - ihr Text steht in mehreren Teilen */
const zaehlzeile = (text: string) => (_: string, element: Element | null) =>
    element?.tagName === 'P' && element.textContent === text;

const DATEN: Spielstaetten = {
    orte: [
        {name: 'Platz A', adresse: 'A-Weg, 99999 A', lat: 50, lon: 11, genauigkeit: 'platz', anzahl: 2,
            spiele: [{datum: '2026-10-10', saison: '26/27', heim: 'A', gast: 'B', rolle: 'SR'},
                {datum: '2026-03-01', saison: '25/26', heim: 'A', gast: 'C', rolle: 'SR'}]},
        {name: 'Platz B', adresse: 'B-Weg, 99998 B', lat: 51, lon: 12, genauigkeit: 'ort', anzahl: 1,
            spiele: [{datum: '2026-02-01', saison: '25/26', heim: 'B', gast: 'D', rolle: null}]},
    ],
    spiele: 3, offen: 0, ohne_treffer: 1,
    kacheln: {url: 'https://tile.example/{z}/{x}/{y}.png', attribution: 'OSM'},
};

beforeEach(() => {
    apiZuruecksetzen();
    marker.length = 0;
});

describe('SpielstaettenKarte', () => {
    it('zeigt alle besuchten Plaetze und grenzt auf die Saison ein', async () => {
        getRouten({'/api/spielstaetten': DATEN});
        render(<SpielstaettenKarte saison="26/27"/>);

        expect(await screen.findByText(zaehlzeile('2 Spielstätten · 3 Einsätze'))).toBeInTheDocument();
        expect(marker).toHaveLength(2);
        expect(screen.getByText(/Ohne Position: 1 Platz/)).toBeInTheDocument();
        // Ungefaehre Lage gestrichelt
        expect(marker.find((m) => m.punkt[0] === 51)?.optionen.dashArray).toBe('3 3');

        marker.length = 0;
        await userEvent.click(screen.getByRole('button', {name: 'Saison 26/27'}));

        expect(screen.getByText(zaehlzeile('1 Spielstätte · 1 Einsatz'))).toBeInTheDocument();
        expect(marker.map((m) => m.punkt)).toEqual([[50, 11]]);
    });

    it('sagt, wenn es noch keinen besuchten Platz gibt', async () => {
        getRouten({'/api/spielstaetten': {...DATEN, orte: [], spiele: 0, ohne_treffer: 0}});
        render(<SpielstaettenKarte saison={null}/>);

        expect(await screen.findByText('Noch kein vergangenes Spiel mit bekannter Spielstätte.')).toBeInTheDocument();
        expect(screen.queryByRole('group', {name: 'Zeitraum der Karte'})).not.toBeInTheDocument();
    });

    it('meldet einen Ladefehler', async () => {
        getRouten({'/api/spielstaetten': new Error('500')});
        render(<SpielstaettenKarte saison="26/27"/>);
        expect(await screen.findByText('Die Karte konnte nicht geladen werden.')).toBeInTheDocument();
    });
});
