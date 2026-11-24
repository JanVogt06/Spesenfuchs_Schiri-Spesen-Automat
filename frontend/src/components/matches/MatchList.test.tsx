import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {render, screen, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {apiZuruecksetzen} from '@/test/apiMock';
import type {MatchData} from '@/lib/matches';
import {MatchList} from './MatchList';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

let naechsteId = 1;

function spiel(datum: string, heim: string, gast = 'SV Gast'): MatchData {
    return {
        _id: naechsteId++,
        _datum: datum,
        spiel_info: {heim_team: heim, gast_team: gast, spielklasse: 'Kreisliga A'},
        schiedsrichter: [],
        spielstaette: {},
    };
}

function zeige(matches: MatchData[]) {
    return render(<MemoryRouter><MatchList matches={matches}/></MemoryRouter>);
}

const knopf = (name: RegExp) => within(screen.getByRole('group', {name: 'Zeitraum'})).getByRole('button', {name});
const monate = () => screen.queryAllByRole('region').map((r) => r.getAttribute('aria-label'));

beforeEach(() => {
    apiZuruecksetzen();
    vi.useFakeTimers({toFake: ['Date']});
    vi.setSystemTime(new Date(2026, 10, 24, 12, 0));
});

afterEach(() => {
    vi.useRealTimers();
});

describe('MatchList - Zeitraum, Suche und Monate', () => {
    const SPIELE = [
        spiel('2026-12-05', 'FC Dezember'),
        spiel('2026-11-28', 'FC November'),
        spiel('2026-11-01', 'FC Vorbei'),
        spiel('2026-10-10', 'FC Oktober'),
    ];

    it('zeigt zuerst die kommenden Spiele nach Monat, mit Anzahl je Zeitraum', () => {
        zeige(SPIELE);

        expect(knopf(/Kommend/)).toHaveAttribute('aria-pressed', 'true');
        expect(knopf(/Kommend/)).toHaveTextContent('2');
        expect(knopf(/Vergangen/)).toHaveTextContent('2');
        expect(monate()).toEqual(['November 2026', 'Dezember 2026']);
        expect(screen.getByText('FC November – SV Gast')).toBeInTheDocument();
        expect(screen.queryByText('FC Vorbei – SV Gast')).not.toBeInTheDocument();
    });

    it('wechselt zu den vergangenen Spielen, juengstes zuerst', async () => {
        const user = userEvent.setup();
        zeige(SPIELE);

        await user.click(knopf(/Vergangen/));

        expect(knopf(/Vergangen/)).toHaveAttribute('aria-pressed', 'true');
        expect(monate()).toEqual(['November 2026', 'Oktober 2026']);
        expect(screen.getByText('FC Vorbei – SV Gast')).toBeInTheDocument();
    });

    it('beginnt ohne kommende Ansetzung bei den vergangenen Spielen', () => {
        zeige([spiel('2026-11-01', 'FC Vorbei')]);

        expect(knopf(/Vergangen/)).toHaveAttribute('aria-pressed', 'true');
        expect(screen.getByText('FC Vorbei – SV Gast')).toBeInTheDocument();
    });

    it('filtert ueber die Suche und passt die Anzahl an', async () => {
        const user = userEvent.setup();
        zeige(SPIELE);

        await user.type(screen.getByRole('searchbox', {name: 'Spiele durchsuchen'}), 'dezember');

        expect(knopf(/Kommend/)).toHaveTextContent('1');
        expect(knopf(/Vergangen/)).toHaveTextContent('0');
        expect(monate()).toEqual(['Dezember 2026']);

        await user.click(knopf(/Vergangen/));
        expect(screen.getByText('Keine vergangenen Spiele zu „dezember“.')).toBeInTheDocument();
    });
});
