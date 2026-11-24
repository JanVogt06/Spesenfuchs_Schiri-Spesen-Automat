import type {Fahrgemeinschaft, RollenPraefix} from '@/lib/matches';

export const ROLLEN: Record<RollenPraefix, string> = {sr: 'SR', sra1: 'SRA 1', sra2: 'SRA 2'};

/** "SRA 1", für die eigene Rolle "SRA 1 (du)" */
export function rollenName(praefix: RollenPraefix, selbst: RollenPraefix | null): string {
    return praefix === selbst ? `${ROLLEN[praefix]} (du)` : ROLLEN[praefix];
}

function aufzaehlen(teile: string[]): string {
    return teile.length <= 1 ? teile.join('') : `${teile.slice(0, -1).join(', ')} und ${teile[teile.length - 1]}`;
}

/** "SR fährt und holt SRA 1 ab (44 km)" / "SRA 2 fährt allein (50 km)" */
export function beschreibeFahrgemeinschaft(vorschlag: Fahrgemeinschaft, selbst: RollenPraefix | null): string[] {
    return vorschlag.fahrten.map((fahrt) => {
        const fahrer = rollenName(fahrt.fahrer, selbst);
        return fahrt.mitfahrer.length > 0
            ? `${fahrer} fährt und holt ${aufzaehlen(fahrt.mitfahrer.map((m) => rollenName(m, selbst)))} ab (${fahrt.km} km)`
            : `${fahrer} fährt allein (${fahrt.km} km)`;
    });
}
