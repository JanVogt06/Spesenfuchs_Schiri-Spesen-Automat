import {useEffect, useState} from 'react';
import {Button} from '@/components/ui/button';
import {getFahrtVorschlaege, type FahrtVorschlaege as Vorschlaege, type RollenPraefix} from '@/lib/matches';
import {beschreibeFahrgemeinschaft, rollenName} from '@/lib/fahrten';
import {Car, Loader2, Route, Users} from 'lucide-react';

interface FahrtVorschlaegeProps {
    matchId: number;
    /** Traegt die Kilometer in die Eingabefelder ein - gespeichert wird erst mit "Speichern" */
    onUebernehmen: (km: Partial<Record<RollenPraefix, number>>) => void;
}

/**
 * Kilometer-Vorschläge für die Fahrtkosten: jede Person allein und als
 * Fahrgemeinschaft. Ein Klick auf "Übernehmen" füllt die Felder darunter.
 */
export function FahrtVorschlaege({matchId, onUebernehmen}: FahrtVorschlaegeProps) {
    const [daten, setDaten] = useState<Vorschlaege | null>(null);
    const [fehler, setFehler] = useState(false);

    useEffect(() => {
        let aktiv = true;
        getFahrtVorschlaege(matchId)
            .then((antwort) => aktiv && setDaten(antwort))
            .catch(() => aktiv && setFehler(true));
        return () => {
            aktiv = false;
        };
    }, [matchId]);

    if (fehler || daten?.quelle === 'gestoert') {
        return (
            <p className="text-xs text-muted-foreground">
                Kilometer-Vorschläge gerade nicht verfügbar – die Adresssuche antwortet nicht.
            </p>
        );
    }

    if (!daten) {
        return (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin"/>
                Berechne Strecken…
            </p>
        );
    }

    const einzeln = Object.entries(daten.einzeln.km) as [RollenPraefix, number][];
    if (daten.ohne_spielort || einzeln.length === 0) {
        return (
            <p className="text-xs text-muted-foreground">
                Für Kilometer-Vorschläge fehlt {daten.ohne_spielort ? 'der Ort der Spielstätte' : 'eine auffindbare Anschrift'}.
            </p>
        );
    }

    return (
        <div role="group" className="space-y-2" aria-label="Kilometer-Vorschläge">
            <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Route className="size-3.5"/>
                Vorschlag, jeweils Hin- und Rückfahrt
            </p>

            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/40 px-3 py-2">
                <div className="min-w-0 text-sm">
                    <p className="flex items-center gap-1.5 font-medium">
                        <Car className="size-3.5 shrink-0 text-muted-foreground"/>
                        Jeder fährt allein
                        <span className="font-normal text-muted-foreground">· {daten.einzeln.gesamt} km</span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                        {einzeln.map(([rolle, km]) => `${rollenName(rolle, daten.selbst)} ${km} km`).join(' · ')}
                    </p>
                </div>
                <Button size="sm" variant="outline" onClick={() => onUebernehmen(daten.einzeln.km)}>
                    Übernehmen
                </Button>
            </div>

            {daten.fahrgemeinschaften.map((vorschlag, index) => (
                <div
                    key={index}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-primary/5 px-3 py-2 ring-1 ring-primary/15"
                >
                    <div className="min-w-0 text-sm">
                        <p className="flex flex-wrap items-center gap-x-1.5 font-medium">
                            <Users className="size-3.5 shrink-0 text-primary"/>
                            Fahrgemeinschaft
                            <span className="font-normal text-muted-foreground">· {vorschlag.gesamt} km</span>
                            <span className="text-xs font-normal text-primary">spart {vorschlag.ersparnis} km</span>
                        </p>
                        {beschreibeFahrgemeinschaft(vorschlag, daten.selbst).map((zeile) => (
                            <p key={zeile} className="text-xs text-muted-foreground">{zeile}</p>
                        ))}
                    </div>
                    <Button size="sm" variant="outline" onClick={() => onUebernehmen(vorschlag.km)}>
                        Übernehmen
                    </Button>
                </div>
            ))}

            {(daten.quelle === 'luftlinie' || daten.ohne_anschrift.length > 0) && (
                <p className="text-xs text-muted-foreground">
                    {daten.quelle === 'luftlinie' && 'Routenplaner nicht erreichbar – grob über die Luftlinie geschätzt. '}
                    {daten.ohne_anschrift.length > 0
                        && `Ohne auffindbare Anschrift: ${daten.ohne_anschrift.join(', ')}.`}
                </p>
            )}
        </div>
    );
}
