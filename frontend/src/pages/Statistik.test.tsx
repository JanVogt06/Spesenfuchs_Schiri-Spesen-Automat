import {beforeEach, describe, expect, it, vi} from 'vitest';
import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {apiGet, apiZuruecksetzen} from '@/test/apiMock';
import {StatistikPage} from './Statistik';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);
vi.mock('@/components/ThemeProvider', () => ({useTheme: () => ({resolvedTheme: 'light'})}));
vi.mock('leaflet', () => {
    const kette = () => {
        const objekt: Record<string, unknown> = {};
        for (const name of ['addTo', 'bindTooltip', 'bindPopup']) objekt[name] = () => objekt;
        return objekt;
    };
    return {default: {
        map: () => ({fitBounds: vi.fn(), invalidateSize: vi.fn(), remove: vi.fn()}),
        tileLayer: kette, circleMarker: kette, latLngBounds: (p: unknown) => p,
    }};
});

function statistik(saison: string) {
    return {
        saisons: ['26/27', '25/26'], saison, quelle: 'dfbnet', spiele: saison === '26/27' ? 3 : 1,
        ohne_rolle: 0, ohne_satz: 0, ohne_ansetzung: 0,
        spesen: saison === '26/27' ? 90 : 25,
        fahrtkosten: {erfasst: 0, erfasst_spiele: 0, geschaetzt: 0, geschaetzt_spiele: 0, geschaetzt_km: 0,
            ohne_schaetzung: 0, luftlinie_spiele: 0, fahrgemeinschaft_spiele: 0, mitfahrer_spiele: 0},
        gesamt: 0, monate: [], rollen: [], offen: 0,
    };
}

beforeEach(() => {
    apiZuruecksetzen();
    apiGet.mockImplementation(async (url: string, config?: unknown) => {
        const saison = (config as {params?: {saison?: string}} | undefined)?.params?.saison;
        if (url === '/api/statistik') return {data: statistik(saison ?? '26/27')};
        if (url === '/api/spielstaetten') {
            return {data: {orte: [], spiele: 0, offen: 0, ohne_treffer: 0, kacheln: {url: '', attribution: ''}}};
        }
        if (url === '/api/scrape/status') return {data: {status: 'idle', progress: null}};
        if (url === '/api/auth/me') return {data: {user_id: 1, dfb_login_abgelehnt_seit: null}};
        throw new Error(`Unerwarteter GET ${url}`);
    });
});

describe('StatistikPage', () => {
    it('zeigt die neueste Saison und wechselt ueber die Saisonauswahl', async () => {
        render(<MemoryRouter><StatistikPage/></MemoryRouter>);

        expect(await screen.findByRole('heading', {level: 1, name: 'Statistik'})).toBeInTheDocument();
        expect(await screen.findByText(/90,00/)).toBeInTheDocument();
        const auswahl = within(screen.getByRole('group', {name: 'Saison'}));
        expect(auswahl.getByRole('button', {name: '26/27'})).toHaveAttribute('aria-pressed', 'true');

        await userEvent.click(auswahl.getByRole('button', {name: '25/26'}));

        expect(await screen.findByText(/25,00/)).toBeInTheDocument();
        expect(apiGet).toHaveBeenCalledWith('/api/statistik', {params: {saison: '25/26'}});
        expect(auswahl.getByRole('button', {name: '25/26'})).toHaveAttribute('aria-pressed', 'true');
        expect(screen.getByText('Besuchte Spielstätten')).toBeInTheDocument();
    });
});
