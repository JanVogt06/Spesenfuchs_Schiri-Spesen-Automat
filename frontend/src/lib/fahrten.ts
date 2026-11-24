import type {Fahrgemeinschaft, RollenPraefix, Treffpunkt} from '@/lib/matches';

export const ROLLEN: Record<RollenPraefix, string> = {sr: 'SR', sra1: 'SRA 1', sra2: 'SRA 2'};

/** "SRA 1", for the user's own role "SRA 1 (du)" */
export function rollenName(praefix: RollenPraefix, selbst: RollenPraefix | null): string {
    return praefix === selbst ? `${ROLLEN[praefix]} (du)` : ROLLEN[praefix];
}

function aufzaehlen(teile: string[]): string {
    return teile.length <= 1 ? teile.join('') : `${teile.slice(0, -1).join(', ')} und ${teile[teile.length - 1]}`;
}

/** One car of a suggestion as a line of text, plus its meeting point if it has one */
export interface FahrtZeile {
    text: string;
    treffpunkt: Treffpunkt | null;
}

/**
 * Describes the cars of a suggestion, e.g.
 * "SR fährt und holt SRA 1 ab (44 km)",
 * "SR fährt (60 km), SRA 1 kommt zum Treffpunkt etwa bei Kahla (4 km)",
 * "SRA 2 fährt allein (50 km)".
 */
export function beschreibeFahrgemeinschaft(vorschlag: Fahrgemeinschaft, selbst: RollenPraefix | null): FahrtZeile[] {
    return vorschlag.fahrten.map((fahrt) => {
        const fahrer = rollenName(fahrt.fahrer, selbst);
        if (fahrt.treffpunkt) {
            const ort = fahrt.treffpunkt.name ? `etwa bei ${fahrt.treffpunkt.name}` : 'unterwegs';
            const zubringer = fahrt.mitfahrer.map((m) => `${rollenName(m, selbst)} (${fahrt.zubringer?.[m] ?? 0} km)`);
            const verb = fahrt.mitfahrer.length === 1 ? 'kommt' : 'kommen';
            return {
                text: `${fahrer} fährt (${fahrt.km} km), ${aufzaehlen(zubringer)} ${verb} zum Treffpunkt ${ort}`,
                treffpunkt: fahrt.treffpunkt,
            };
        }
        const text = fahrt.mitfahrer.length > 0
            ? `${fahrer} fährt und holt ${aufzaehlen(fahrt.mitfahrer.map((m) => rollenName(m, selbst)))} ab (${fahrt.km} km)`
            : `${fahrer} fährt allein (${fahrt.km} km)`;
        return {text, treffpunkt: null};
    });
}

/** Link to the meeting point on openstreetmap.org - it is only approximate, so zoomed out a bit */
export function treffpunktLink(treffpunkt: Treffpunkt): string {
    const lat = treffpunkt.lat.toFixed(4);
    const lon = treffpunkt.lon.toFixed(4);
    return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=13/${lat}/${lon}`;
}
