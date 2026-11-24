import type {MatchData} from './matches';

/** Today as an ISO date - the matches also carry their date as "YYYY-MM-DD" */
export function heuteIso(jetzt: Date = new Date()): string {
    return `${jetzt.getFullYear()}-${String(jetzt.getMonth() + 1).padStart(2, '0')}-${String(jetzt.getDate()).padStart(2, '0')}`;
}

/** Kickoff time as "HH:MM" for sorting - two matches on the same day */
export function anstoss(match: MatchData): string {
    const treffer = /(\d{1,2}):(\d{2})/.exec(match.spiel_info?.anpfiff || '');
    return treffer ? `${treffer[1].padStart(2, '0')}:${treffer[2]}` : '99:99';
}

function frueherZuerst(a: MatchData, b: MatchData): number {
    return (a._datum || '').localeCompare(b._datum || '') || anstoss(a).localeCompare(anstoss(b));
}

/**
 * Upcoming matches (from today) with the next one first, past ones with the
 * most recent first. A match without a date cannot be placed and
 * goes at the very end of the past ones.
 */
export function teileSpiele(matches: MatchData[], heute: string): {kommend: MatchData[]; vergangen: MatchData[]} {
    const kommend = matches.filter((m) => m._datum && m._datum >= heute).sort(frueherZuerst);
    const vergangen = matches
        .filter((m) => !m._datum || m._datum < heute)
        .sort((a, b) => {
            if (!a._datum !== !b._datum) return a._datum ? -1 : 1;
            return frueherZuerst(b, a);
        });
    return {kommend, vergangen};
}

/** Searches clubs, league class, team type and venue; case-insensitive */
export function passtZurSuche(match: MatchData, suche: string): boolean {
    const woerter = suche.toLocaleLowerCase('de-DE').split(/\s+/).filter(Boolean);
    if (woerter.length === 0) return true;

    const info = match.spiel_info ?? {};
    const text = [
        info.heim_team, info.gast_team, info.spielklasse, info.mannschaftsart, info.staffel,
        match.spielstaette?.name, match.spielstaette?.adresse,
    ].filter(Boolean).join(' ').toLocaleLowerCase('de-DE');

    // Every word must occur somewhere - "jena kreisliga" finds the match in Jena of the Kreisliga
    return woerter.every((wort) => text.includes(wort));
}

export interface Monatsgruppe {
    schluessel: string;
    titel: string;
    spiele: MatchData[];
}

/** Groups the (already sorted) matches by month, order is preserved */
export function nachMonat(matches: MatchData[]): Monatsgruppe[] {
    const gruppen: Monatsgruppe[] = [];
    for (const match of matches) {
        const schluessel = /^\d{4}-\d{2}/.exec(match._datum || '')?.[0] ?? 'ohne-datum';
        let gruppe = gruppen[gruppen.length - 1];
        if (!gruppe || gruppe.schluessel !== schluessel) {
            const titel = schluessel === 'ohne-datum'
                ? 'Ohne Datum'
                : new Date(Number(schluessel.slice(0, 4)), Number(schluessel.slice(5, 7)) - 1, 1)
                    .toLocaleDateString('de-DE', {month: 'long', year: 'numeric'});
            gruppe = {schluessel, titel, spiele: []};
            gruppen.push(gruppe);
        }
        gruppe.spiele.push(match);
    }
    return gruppen;
}
