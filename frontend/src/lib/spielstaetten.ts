import {api} from './api';

export interface Besuch {
    datum: string;
    saison: string;
    heim: string;
    gast: string;
    /** Eigene Rolle, wenn sie sich zuordnen ließ */
    rolle: string | null;
}

export interface BesuchterOrt {
    name: string;
    adresse: string;
    lat: number;
    lon: number;
    /** platz: Koordinate aus DFBnet; adresse/ort: über die Adresssuche */
    genauigkeit: 'platz' | 'adresse' | 'ort';
    anzahl: number;
    /** Neueste zuerst */
    spiele: Besuch[];
}

export interface Spielstaetten {
    orte: BesuchterOrt[];
    spiele: number;
    offen: number;
    ohne_treffer: number;
    kacheln: {url: string; attribution: string};
}

export async function getSpielstaetten(): Promise<Spielstaetten> {
    const response = await api.get<Spielstaetten>('/api/spielstaetten');
    return response.data;
}

/** Nur die Orte - und an ihnen nur die Spiele - einer Saison; null heißt alle */
export function inSaison(orte: BesuchterOrt[], saison: string | null): BesuchterOrt[] {
    if (!saison) return orte;
    return orte
        .map((ort) => {
            const spiele = ort.spiele.filter((s) => s.saison === saison);
            return {...ort, spiele, anzahl: spiele.length};
        })
        .filter((ort) => ort.anzahl > 0);
}

function escapeHtml(text: string): string {
    return text.replace(/[&<>"']/g, (zeichen) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[zeichen] as string));
}

function datum(iso: string): string {
    const [jahr, monat, tag] = iso.split('-');
    return tag ? `${tag}.${monat}.${jahr}` : iso;
}

const MAX_SPIELE_IM_POPUP = 6;

/** Inhalt des Popups eines Ortes als HTML für Leaflet */
export function ortPopup(ort: BesuchterOrt): string {
    const spiele = ort.spiele.slice(0, MAX_SPIELE_IM_POPUP).map((s) => {
        const paarung = s.heim && s.gast ? `${s.heim} – ${s.gast}` : s.heim || 'Turnier';
        const rolle = s.rolle ? ` · ${escapeHtml(s.rolle)}` : '';
        return `<div>${datum(s.datum)} · ${escapeHtml(paarung)}${rolle}</div>`;
    }).join('');
    const mehr = ort.spiele.length > MAX_SPIELE_IM_POPUP
        ? `<div style="opacity:.7">… und ${ort.spiele.length - MAX_SPIELE_IM_POPUP} weitere</div>`
        : '';
    const ungefaehr = ort.genauigkeit === 'ort'
        ? '<div style="margin-top:4px;opacity:.7">Ungefähre Lage: nur der Ort war auffindbar.</div>'
        : '';
    return `<div style="font-size:12px;line-height:1.5">
        <strong>${escapeHtml(ort.name)}</strong>
        <div style="opacity:.75">${escapeHtml(ort.adresse)}</div>
        <div style="margin:4px 0 2px">${ort.anzahl} ${ort.anzahl === 1 ? 'Einsatz' : 'Einsätze'}</div>
        ${spiele}${mehr}${ungefaehr}</div>`;
}
