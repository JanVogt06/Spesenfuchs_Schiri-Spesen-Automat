import type {MatchData} from './matches';

/** Heute als ISO-Datum - die Spiele tragen ihr Datum ebenfalls als "YYYY-MM-DD" */
export function heuteIso(jetzt: Date = new Date()): string {
    return `${jetzt.getFullYear()}-${String(jetzt.getMonth() + 1).padStart(2, '0')}-${String(jetzt.getDate()).padStart(2, '0')}`;
}

/** Anstosszeit als "HH:MM" zum Sortieren - zwei Spiele am selben Tag */
export function anstoss(match: MatchData): string {
    const treffer = /(\d{1,2}):(\d{2})/.exec(match.spiel_info?.anpfiff || '');
    return treffer ? `${treffer[1].padStart(2, '0')}:${treffer[2]}` : '99:99';
}

function frueherZuerst(a: MatchData, b: MatchData): number {
    return (a._datum || '').localeCompare(b._datum || '') || anstoss(a).localeCompare(anstoss(b));
}

/**
 * Kommende Spiele (ab heute) mit dem naechsten zuerst, vergangene mit dem
 * juengsten zuerst. Ein Spiel ohne Datum laesst sich nicht einordnen und
 * steht ganz hinten bei den vergangenen.
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

/** Sucht in Vereinen, Spielklasse, Mannschaftsart und Spielstaette; Gross-/Kleinschreibung egal */
export function passtZurSuche(match: MatchData, suche: string): boolean {
    const woerter = suche.toLocaleLowerCase('de-DE').split(/\s+/).filter(Boolean);
    if (woerter.length === 0) return true;

    const info = match.spiel_info ?? {};
    const text = [
        info.heim_team, info.gast_team, info.spielklasse, info.mannschaftsart, info.staffel,
        match.spielstaette?.name, match.spielstaette?.adresse,
    ].filter(Boolean).join(' ').toLocaleLowerCase('de-DE');

    // Jedes Wort muss irgendwo vorkommen - "jena kreisliga" findet das Spiel in Jena der Kreisliga
    return woerter.every((wort) => text.includes(wort));
}

export interface Monatsgruppe {
    schluessel: string;
    titel: string;
    spiele: MatchData[];
}

/** Fasst die (schon sortierten) Spiele nach Monat zusammen, Reihenfolge bleibt */
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
