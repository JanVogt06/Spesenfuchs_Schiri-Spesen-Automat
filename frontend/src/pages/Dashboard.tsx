import {useState, useEffect, useCallback, useMemo} from 'react';
import {useNavigate} from 'react-router-dom';
import {Button} from '@/components/ui/button';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Separator} from '@/components/ui/separator';
import {Badge} from '@/components/ui/badge';
import {AppShell} from '@/components/layout/AppShell';
import {GenerateButton} from '@/components/matches/GenerateButton';
import {useScrapeRun} from '@/hooks/useScrapeRun';
import {getAllMatches, type MatchData} from '@/lib/matches';
import {getSaisons, getSaison, type SaisonDetails} from '@/lib/saison';
import {
    AlertCircle, Loader2, Calendar, Receipt, Trophy, SquareStack,
    ArrowRight, MapPin,
} from 'lucide-react';

/** Heute als ISO-Datum - die Spiele tragen ihr Datum ebenfalls als "YYYY-MM-DD" */
function heuteIso(): string {
    const jetzt = new Date();
    return `${jetzt.getFullYear()}-${String(jetzt.getMonth() + 1).padStart(2, '0')}-${String(jetzt.getDate()).padStart(2, '0')}`;
}

function formatDatum(iso?: string): string {
    if (!iso) return '';
    const teile = iso.split('-');
    return teile.length === 3 ? `${teile[2]}.${teile[1]}.${teile[0]}` : iso;
}

/** Ob zu einem Spiel schon Fahrtkosten erfasst sind */
function hatSpesen(match: MatchData): boolean {
    const e = match._expenses;
    if (!e) return false;
    return [e.sr_km, e.sr_oevm, e.sra1_km, e.sra1_oevm, e.sra2_km, e.sra2_oevm]
        .some((wert) => wert !== null && wert !== undefined);
}

interface KennzahlProps {
    icon: typeof Calendar;
    label: string;
    wert: string;
    zusatz?: string;
}

function Kennzahl({icon: Icon, label, wert, zusatz}: KennzahlProps) {
    return (
        <Card className="gap-0 py-0">
            <CardContent className="flex items-start gap-3 p-4">
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="size-4"/>
                </span>
                <div className="min-w-0">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="truncate text-xl font-semibold tabular-nums">{wert}</p>
                    {zusatz && <p className="truncate text-xs text-muted-foreground">{zusatz}</p>}
                </div>
            </CardContent>
        </Card>
    );
}

export function DashboardPage() {
    const navigate = useNavigate();
    const [matches, setMatches] = useState<MatchData[]>([]);
    const [saison, setSaison] = useState<SaisonDetails | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [ladeFehler, setLadeFehler] = useState('');

    const loadAlles = useCallback(async () => {
        try {
            // Beide Quellen parallel; die Saisondaten sind optional, das
            // Dashboard soll auch ohne sie etwas zeigen.
            const [spiele, saisons] = await Promise.all([
                getAllMatches(),
                getSaisons().catch(() => []),
            ]);
            setMatches(spiele);

            if (saisons.length > 0) {
                setSaison(await getSaison(saisons[0].saison).catch(() => null));
            } else {
                setSaison(null);
            }
            setLadeFehler('');
        } catch (err: unknown) {
            const detail = (err as {response?: {data?: {error?: {message?: string}}}})
                ?.response?.data?.error?.message;
            setLadeFehler(detail || 'Die Übersicht konnte nicht geladen werden.');
        } finally {
            setIsLoading(false);
        }
    }, []);

    const {run, isRunning, isStarting, error, startGeneration} = useScrapeRun(loadAlles);

    useEffect(() => {
        loadAlles();
    }, [loadAlles]);

    const heute = heuteIso();

    const naechste = useMemo(
        () => matches
            .filter((m) => (m._datum || '') >= heute && !m._missing_since)
            .sort((a, b) => (a._datum || '').localeCompare(b._datum || ''))
            .slice(0, 3),
        [matches, heute],
    );

    const offeneSpesen = useMemo(
        () => matches.filter((m) => (m._datum || '') < heute && !m._missing_since && !hatSpesen(m)),
        [matches, heute],
    );

    /** Karten pro Spiel in der laufenden Saison, über beide Mannschaften */
    const kartenSchnitt = useMemo(() => {
        const spiele = saison?.spiele ?? [];
        if (spiele.length === 0) return null;

        const summe = spiele.reduce((gesamt, spiel) => gesamt
            + (spiel.heim_gelb ?? 0) + (spiel.heim_gelbrot ?? 0) + (spiel.heim_rot ?? 0)
            + (spiel.gast_gelb ?? 0) + (spiel.gast_gelbrot ?? 0) + (spiel.gast_rot ?? 0), 0);

        return {
            schnitt: summe / spiele.length,
            summe,
            rot: spiele.reduce((g, s) => g + (s.heim_gelbrot ?? 0) + (s.heim_rot ?? 0)
                + (s.gast_gelbrot ?? 0) + (s.gast_rot ?? 0), 0),
        };
    }, [saison]);

    const displayError = error || ladeFehler;
    const istAnmeldefehler = run?.progress?.error_code === 'DFB_CREDENTIALS_INVALID';

    return (
        <AppShell actions={<GenerateButton isGenerating={isStarting || isRunning} onClick={startGeneration}/>}>
            {displayError && (
                <div className="mb-6 flex items-start gap-2 rounded-lg bg-destructive/10 px-4 py-3 ring-1 ring-destructive/20">
                    <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                    <p className="text-sm break-words text-destructive">{displayError}</p>
                </div>
            )}

            {run?.status === 'failed' && istAnmeldefehler && (
                <div className="mb-6 flex items-start gap-3 rounded-lg bg-destructive/10 px-4 py-3 ring-1 ring-destructive/20">
                    <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                    <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-destructive">DFBnet-Login fehlgeschlagen</p>
                        <p className="mt-0.5 text-sm text-destructive/80">
                            {run.progress?.error_message || 'Bitte prüfe deine Zugangsdaten.'}
                        </p>
                        <Button variant="destructive" size="sm" className="mt-2" onClick={() => navigate('/settings')}>
                            Zugangsdaten prüfen
                        </Button>
                    </div>
                </div>
            )}

            {isRunning && (
                <div className="mb-6 flex items-start gap-2 rounded-lg border bg-muted/30 px-4 py-3">
                    <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-muted-foreground"/>
                    <p className="text-sm text-muted-foreground">
                        {run?.progress?.step || 'Aktualisierung läuft...'} Die Übersicht aktualisiert sich
                        automatisch, sobald der Abruf fertig ist.
                    </p>
                </div>
            )}

            {isLoading ? (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-sm text-muted-foreground">
                    <Loader2 className="size-5 animate-spin"/>
                    Lade Übersicht...
                </div>
            ) : (
                <div className="space-y-4">
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                        <Kennzahl
                            icon={Trophy}
                            label={saison ? `Spiele in ${saison.saison}` : 'Geleitete Spiele'}
                            wert={saison ? String(saison.spiele.length) : '–'}
                            zusatz={saison ? 'laufende Saison' : 'noch kein Abruf'}
                        />
                        <Kennzahl
                            icon={SquareStack}
                            label="Kartenschnitt"
                            wert={kartenSchnitt ? kartenSchnitt.schnitt.toFixed(1) : '–'}
                            zusatz={kartenSchnitt
                                ? `${kartenSchnitt.summe} Karten, davon ${kartenSchnitt.rot} Platzverweise`
                                : 'pro Spiel, laufende Saison'}
                        />
                        <Kennzahl
                            icon={Calendar}
                            label="Nächstes Spiel"
                            wert={naechste.length > 0 ? formatDatum(naechste[0]._datum) : '–'}
                            zusatz={naechste.length > 0
                                ? naechste[0].spiel_info.spielklasse || 'Ansetzung'
                                : 'keine offene Ansetzung'}
                        />
                        <Kennzahl
                            icon={Receipt}
                            label="Ohne Kilometer"
                            wert={String(offeneSpesen.length)}
                            zusatz={offeneSpesen.length === 0
                                ? 'alles erfasst'
                                : 'gespielt, aber nichts eingetragen'}
                        />
                    </div>

                    <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
                        <Card className="gap-0 overflow-hidden py-0">
                            <CardHeader className="flex h-11 flex-row items-center justify-between gap-2 px-4 py-0 sm:px-6">
                                <div className="flex items-center gap-2">
                                    <Calendar className="size-4 text-muted-foreground"/>
                                    <CardTitle className="text-sm">Nächste Ansetzungen</CardTitle>
                                </div>
                                <Button variant="ghost" size="sm" onClick={() => navigate('/spesen')}>
                                    Alle Spiele
                                    <ArrowRight className="size-3.5"/>
                                </Button>
                            </CardHeader>
                            <Separator/>
                            <CardContent className="p-4 sm:p-6">
                                {naechste.length === 0 ? (
                                    <p className="text-sm text-muted-foreground">
                                        Zurzeit steht keine kommende Ansetzung in deinem DFBnet-Konto.
                                    </p>
                                ) : (
                                    <div className="space-y-3">
                                        {naechste.map((match) => {
                                            const info = match.spiel_info;
                                            const eigene = match.schiedsrichter?.find(
                                                (person) => person.rolle && person.name,
                                            );
                                            return (
                                                <div
                                                    key={match._id}
                                                    className="rounded-lg border border-dashed p-3 text-sm"
                                                >
                                                    <div className="flex items-start justify-between gap-2">
                                                        <p className="min-w-0 font-medium break-words">
                                                            {info.heim_team && info.gast_team
                                                                ? `${info.heim_team} – ${info.gast_team}`
                                                                : 'Turnier'}
                                                        </p>
                                                        <span className="shrink-0 text-xs whitespace-nowrap text-muted-foreground">
                                                            {formatDatum(match._datum)}
                                                        </span>
                                                    </div>
                                                    <p className="mt-0.5 text-xs text-muted-foreground">
                                                        {[info.spielklasse, info.mannschaftsart].filter(Boolean).join(' · ')}
                                                    </p>
                                                    {match.spielstaette?.name && (
                                                        <p className="mt-1 flex items-center gap-1.5 text-xs break-words text-muted-foreground">
                                                            <MapPin className="size-3 shrink-0"/>
                                                            {match.spielstaette.name}
                                                        </p>
                                                    )}
                                                    {eigene?.rolle && (
                                                        <Badge variant="secondary" className="mt-2 font-normal">
                                                            {eigene.rolle}
                                                        </Badge>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        <Card className="gap-0 overflow-hidden py-0">
                            <CardHeader className="flex h-11 flex-row items-center justify-between gap-2 px-4 py-0 sm:px-6">
                                <div className="flex items-center gap-2">
                                    <Trophy className="size-4 text-muted-foreground"/>
                                    <CardTitle className="text-sm">
                                        {saison ? `Saison ${saison.saison}` : 'Saison'}
                                    </CardTitle>
                                </div>
                                <Button variant="ghost" size="sm" onClick={() => navigate('/saison')}>
                                    Details
                                    <ArrowRight className="size-3.5"/>
                                </Button>
                            </CardHeader>
                            <Separator/>
                            <CardContent className="p-4 sm:p-6">
                                {!saison ? (
                                    <p className="text-sm text-muted-foreground">
                                        Noch keine Saisondaten abgerufen.
                                    </p>
                                ) : (
                                    <div className="space-y-1.5 text-sm">
                                        {saison.einsaetze
                                            .filter((e) => e.geleitet && e.geleitet !== '-')
                                            .map((eintrag) => (
                                                <div key={eintrag.rolle} className="grid grid-cols-[1fr_auto] gap-2">
                                                    <span className="text-muted-foreground">{eintrag.rolle}</span>
                                                    <span className="font-mono">{eintrag.geleitet}</span>
                                                </div>
                                            ))}
                                        {saison.lehrgaenge && (
                                            <>
                                                <Separator className="my-2"/>
                                                <div className="grid grid-cols-[1fr_auto] gap-2">
                                                    <span className="text-muted-foreground">Lehrabende</span>
                                                    <span className="font-mono">
                                                        {saison.lehrgaenge.lehrabend || '–'}
                                                    </span>
                                                </div>
                                                <div className="grid grid-cols-[1fr_auto] gap-2">
                                                    <span className="text-muted-foreground">Leistungsprüfung</span>
                                                    <span className="font-mono">
                                                        {saison.lehrgaenge.leistungspruefung || '–'}
                                                    </span>
                                                </div>
                                            </>
                                        )}
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>

                    {offeneSpesen.length > 0 && (
                        <Card className="gap-0 overflow-hidden py-0">
                            <CardHeader className="flex h-11 flex-row items-center justify-between gap-2 px-4 py-0 sm:px-6">
                                <div className="flex items-center gap-2">
                                    <Receipt className="size-4 text-muted-foreground"/>
                                    <CardTitle className="text-sm">Noch ohne Kilometer</CardTitle>
                                </div>
                                <Button variant="ghost" size="sm" onClick={() => navigate('/spesen')}>
                                    Eintragen
                                    <ArrowRight className="size-3.5"/>
                                </Button>
                            </CardHeader>
                            <Separator/>
                            <CardContent className="p-4 sm:p-6">
                                <div className="space-y-1.5 text-sm">
                                    {offeneSpesen.slice(0, 5).map((match) => (
                                        <div key={match._id} className="flex items-baseline justify-between gap-3">
                                            <span className="min-w-0 truncate">
                                                {match.spiel_info.heim_team && match.spiel_info.gast_team
                                                    ? `${match.spiel_info.heim_team} – ${match.spiel_info.gast_team}`
                                                    : 'Turnier'}
                                            </span>
                                            <span className="shrink-0 text-xs whitespace-nowrap text-muted-foreground">
                                                {formatDatum(match._datum)}
                                            </span>
                                        </div>
                                    ))}
                                    {offeneSpesen.length > 5 && (
                                        <p className="pt-1 text-xs text-muted-foreground">
                                            … und {offeneSpesen.length - 5} weitere
                                        </p>
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </div>
            )}
        </AppShell>
    );
}
