import {useEffect, useState, type ReactNode} from 'react';
import {useNavigate, useParams, useSearchParams} from 'react-router-dom';
import {AppShell} from '@/components/layout/AppShell';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Separator} from '@/components/ui/separator';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {
    AlertCircle, ArrowLeft, ArrowLeftRight, ClipboardList, Download, Euro, ExternalLink, FileText,
    Goal, ListChecks, Loader2, MapPin, Paperclip, Shirt, Timer, Users,
} from 'lucide-react';
import {cn} from '@/lib/utils';
import {extractApiError} from '@/lib/matches';
import {
    downloadDokument, EREIGNIS_NAMEN, formatEuro, getSpielbericht, minuteText, oeffneDokument,
    uhrzeitAus, zeitpunktText,
    type Aufstellung, type Ereignis, type Spieler, type Spielbericht, type SpielberichtDokument,
} from '@/lib/spielberichte';

function formatDatum(iso: string): string {
    const teile = (iso || '').split('-');
    return teile.length === 3 ? `${teile[2]}.${teile[1]}.${teile[0]}` : iso;
}

function Abschnitt({titel, icon: Icon, rechts, children, className}: {
    titel: string;
    icon: typeof Users;
    rechts?: ReactNode;
    children: ReactNode;
    className?: string;
}) {
    return (
        <Card className={cn('gap-0 overflow-hidden py-0', className)}>
            <CardHeader className="flex h-11 flex-row items-center justify-between gap-2 px-4 py-0 sm:px-6">
                <div className="flex items-center gap-2">
                    <Icon className="size-4 text-muted-foreground"/>
                    <CardTitle className="text-sm">{titel}</CardTitle>
                </div>
                {rechts}
            </CardHeader>
            <Separator/>
            <CardContent className="p-4 sm:px-6">{children}</CardContent>
        </Card>
    );
}

/** Das Symbol eines Ereignisses: Karten als kleine Karte, sonst ein Icon */
function EreignisSymbol({typ}: {typ: string}) {
    if (typ === 'gelb') return <span className="inline-block h-4 w-3 rounded-[2px] bg-yellow-400" aria-hidden/>;
    if (typ === 'rot') return <span className="inline-block h-4 w-3 rounded-[2px] bg-red-600" aria-hidden/>;
    if (typ === 'gelbrot') {
        return (
            <span className="inline-block h-4 w-3 overflow-hidden rounded-[2px]" aria-hidden>
                <span className="block h-1/2 bg-yellow-400"/>
                <span className="block h-1/2 bg-red-600"/>
            </span>
        );
    }
    if (typ === 'wechsel') return <ArrowLeftRight className="size-4 text-muted-foreground" aria-hidden/>;
    if (typ === 'zeitstrafe') return <Timer className="size-4 text-muted-foreground" aria-hidden/>;
    if (typ.includes('tor') || typ === 'elfmeterschiessen') return <Goal className="size-4 text-primary" aria-hidden/>;
    return <span className="inline-block size-2 rounded-full bg-muted-foreground" aria-hidden/>;
}

function personText(name: string, nummer: number | null | undefined): string {
    return nummer !== null && nummer !== undefined ? `${name} (${nummer})` : name;
}

function EreignisZeile({e}: {e: Ereignis}) {
    const gast = e.seite === 'gast';
    return (
        <li className={cn('flex items-start gap-3 py-2', gast && 'sm:flex-row-reverse sm:text-right')}>
            <span className="w-12 shrink-0 font-mono text-xs text-muted-foreground sm:w-14">{minuteText(e)}</span>
            <span className="mt-0.5 grid w-4 shrink-0 place-items-center">
                <EreignisSymbol typ={e.typ}/>
            </span>
            <div className="min-w-0 flex-1 text-sm">
                {e.typ === 'wechsel' ? (
                    <p className="break-words">
                        <span className="text-success">▲ {personText(e.person, e.nummer)}</span>
                        <span className="mx-1.5 text-muted-foreground">für</span>
                        <span className="text-destructive">▼ {personText(e.person_raus || '', e.nummer_raus)}</span>
                    </p>
                ) : (
                    <p className="break-words">
                        <span className="font-medium">{personText(e.person, e.nummer)}</span>
                        {e.funktion && <span className="text-muted-foreground"> · {e.funktion}</span>}
                    </p>
                )}
                <p className="text-xs text-muted-foreground">
                    {EREIGNIS_NAMEN[e.typ] ?? e.typ}
                    {e.grund && ` · ${e.grund}`}
                    {e.sonderbericht && (
                        <Badge variant="destructive" className="ml-1.5 align-middle">Sonderbericht</Badge>
                    )}
                </p>
            </div>
            {/* Am Handy steht die Mannschaft dabei - die Seiten-Anordnung gibt es erst ab sm */}
            <span className="shrink-0 text-xs text-muted-foreground sm:hidden">{gast ? 'Gast' : 'Heim'}</span>
        </li>
    );
}

function sortiereSpieler(liste: Spieler[]): Spieler[] {
    return [...liste].sort((a, b) => Number(b.torwart) - Number(a.torwart) || (a.nummer ?? 99) - (b.nummer ?? 99));
}

function SpielerListe({liste}: {liste: Spieler[]}) {
    return (
        <ul className="space-y-0.5 text-sm">
            {sortiereSpieler(liste).map((s) => (
                <li key={s.id} className="flex gap-2">
                    <span className="w-6 shrink-0 text-right font-mono text-xs leading-5 text-muted-foreground">
                        {s.nummer ?? ''}
                    </span>
                    <span className="min-w-0 break-words">
                        {s.name}
                        {s.kapitaen && <span className="ml-1 text-xs font-medium text-primary">(K)</span>}
                        {s.torwart && <span className="ml-1 text-xs text-muted-foreground">TW</span>}
                    </span>
                </li>
            ))}
        </ul>
    );
}

function AufstellungsSpalte({titel, aufstellung}: {titel: string; aufstellung: Aufstellung}) {
    const start = aufstellung.spieler.filter((s) => !s.ersatz);
    const ersatz = aufstellung.spieler.filter((s) => s.ersatz);

    return (
        <div className="min-w-0 space-y-3">
            <p className="text-sm font-medium break-words">{titel}</p>
            {aufstellung.spieler.length === 0 ? (
                <p className="text-sm text-muted-foreground">Keine Aufstellung im Bericht.</p>
            ) : (
                <>
                    <SpielerListe liste={start}/>
                    {ersatz.length > 0 && (
                        <div>
                            <p className="mb-1 text-xs tracking-wide text-muted-foreground uppercase">Ersatzbank</p>
                            <SpielerListe liste={ersatz}/>
                        </div>
                    )}
                </>
            )}
            {aufstellung.offizielle.length > 0 && (
                <div>
                    <p className="mb-1 text-xs tracking-wide text-muted-foreground uppercase">Teamoffizielle</p>
                    <ul className="space-y-0.5 text-sm">
                        {aufstellung.offizielle.map((o) => (
                            <li key={o.id} className="break-words">
                                {o.name}
                                {o.funktion && <span className="text-muted-foreground"> · {o.funktion}</span>}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}

function Zeile({label, children}: {label: string; children: ReactNode}) {
    return (
        <div className="flex justify-between gap-4 py-1 text-sm">
            <span className="text-muted-foreground">{label}</span>
            <span className="min-w-0 text-right break-words">{children}</span>
        </div>
    );
}

function DokumentZeile({berichtId, dokument}: {berichtId: number; dokument: SpielberichtDokument}) {
    const [laedt, setLaedt] = useState<'oeffnen' | 'laden' | null>(null);
    const [fehler, setFehler] = useState('');

    const ausfuehren = async (art: 'oeffnen' | 'laden') => {
        setLaedt(art);
        setFehler('');
        try {
            if (art === 'oeffnen') await oeffneDokument(berichtId, dokument);
            else await downloadDokument(berichtId, dokument);
        } catch (err) {
            setFehler(await extractApiError(err, 'Das Dokument konnte nicht geladen werden.'));
        } finally {
            setLaedt(null);
        }
    };

    const istPdf = dokument.dateiname.toLowerCase().endsWith('.pdf');

    return (
        <li className="flex flex-col gap-2 py-3">
            <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                    <FileText className="size-4 shrink-0 text-muted-foreground"/>
                    <span className="min-w-0 text-sm font-medium break-words">{dokument.dateiname}</span>
                    {dokument.kategorie && <Badge variant="secondary">{dokument.kategorie}</Badge>}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                    {dokument.beschreibung && `${dokument.beschreibung} · `}
                    {dokument.hochgeladen_von && `${dokument.hochgeladen_von}, `}
                    {zeitpunktText(dokument.hochgeladen_am)}
                    {dokument.groesse > 0 && ` · ${Math.max(1, Math.round(dokument.groesse / 1024))} KB`}
                </p>
                {fehler && <p className="mt-1 text-xs text-destructive">{fehler}</p>}
            </div>
            <div className="flex shrink-0 gap-2">
                {istPdf && (
                    <Button variant="outline" size="sm" onClick={() => ausfuehren('oeffnen')} disabled={!!laedt}>
                        {laedt === 'oeffnen' ? <Loader2 className="size-4 animate-spin"/> : <ExternalLink className="size-4"/>}
                        Öffnen
                    </Button>
                )}
                <Button variant="outline" size="sm" onClick={() => ausfuehren('laden')} disabled={!!laedt}>
                    {laedt === 'laden' ? <Loader2 className="size-4 animate-spin"/> : <Download className="size-4"/>}
                    Herunterladen
                </Button>
            </div>
        </li>
    );
}

export function SpielberichtPage() {
    const {id} = useParams();
    const [suche] = useSearchParams();
    const von = suche.get('von');
    const navigate = useNavigate();
    const [bericht, setBericht] = useState<Spielbericht | null>(null);
    const [fehler, setFehler] = useState('');

    useEffect(() => {
        let aktiv = true;
        getSpielbericht(Number(id), von)
            .then((b) => aktiv && setBericht(b))
            .catch(async (err) => aktiv && setFehler(await extractApiError(err, 'Der Spielbericht konnte nicht geladen werden.')));
        return () => {
            aktiv = false;
        };
    }, [id, von]);

    const zurueck = (
        <Button variant="ghost" size="sm" className="-ml-2 mb-3 text-muted-foreground" onClick={() => navigate(-1)}>
            <ArrowLeft className="size-4"/>
            Zurück
        </Button>
    );

    if (fehler) {
        return (
            <AppShell>
                {zurueck}
                <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-4 py-3 ring-1 ring-destructive/20">
                    <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                    <p className="text-sm text-destructive">{fehler}</p>
                </div>
            </AppShell>
        );
    }

    if (!bericht) {
        return (
            <AppShell>
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-sm text-muted-foreground">
                    <Loader2 className="size-5 animate-spin"/>
                    Lade Spielbericht...
                </div>
            </AppShell>
        );
    }

    const d = bericht.daten;
    const ergebnis = d.ergebnis.endstand || bericht.ergebnis || '–';
    const kostenGesamt = (d.kosten.fahrtkosten ?? 0) + (d.kosten.spesen ?? 0);
    const hatKosten = d.kosten.fahrtkosten !== null || d.kosten.spesen !== null;
    const nachspiel = [d.nachspielzeit.h1, d.nachspielzeit.h2, d.nachspielzeit.v1, d.nachspielzeit.v2];
    const v = d.vorkommnisse;

    return (
        <AppShell>
            {zurueck}

            <div className="space-y-4">
                {/* Kopf */}
                <Card className="gap-0 py-0">
                    <CardContent className="space-y-3 p-4 sm:p-6">
                        <p className="text-xs text-muted-foreground break-words">
                            {formatDatum(bericht.datum)}{bericht.uhrzeit && `, ${bericht.uhrzeit}`}
                            {bericht.gruppe && ` · ${bericht.gruppe}`}
                        </p>
                        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
                            <p className="text-sm font-semibold break-words sm:text-base">{bericht.heim || d.heim}</p>
                            <div className="text-center">
                                <p className="font-mono text-2xl font-semibold sm:text-3xl">{ergebnis}</p>
                                {d.ergebnis.halbzeit && (
                                    <p className="text-xs text-muted-foreground">HZ {d.ergebnis.halbzeit}</p>
                                )}
                            </div>
                            <p className="text-right text-sm font-semibold break-words sm:text-base">{bericht.gast || d.gast}</p>
                        </div>
                        {(d.ergebnis.wertung || d.ergebnis.verlaengerung) && (
                            <p className="text-center text-xs text-muted-foreground">
                                {d.ergebnis.wertung}
                                {d.ergebnis.verlaengerung && ` · n.V. ${d.ergebnis.verlaengerung}`}
                                {d.ergebnis.abbruch_minute !== null && ` · Abbruch ${d.ergebnis.abbruch_minute}'`}
                            </p>
                        )}
                        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                            {d.spielkennung && <span>Spielkennung {d.spielkennung}</span>}
                            {d.beginn && (
                                <span>
                                    Anstoß {uhrzeitAus(d.beginn)}
                                    {d.ende && ` · Ende ${uhrzeitAus(d.ende)}`}
                                </span>
                            )}
                            {nachspiel.some((n) => n !== null && n !== undefined) && (
                                <span>
                                    Nachspielzeit {nachspiel.filter((n) => n !== null && n !== undefined).map((n) => `+${n}`).join(' / ')}
                                </span>
                            )}
                            {d.zuschauer !== null && <span>{d.zuschauer.toLocaleString('de-DE')} Zuschauer</span>}
                        </div>
                        {d.spielstaette.name && (
                            <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                                <MapPin className="mt-px size-3.5 shrink-0"/>
                                <span className="break-words">
                                    {d.spielstaette.name}
                                    {d.spielstaette.strasse && `, ${d.spielstaette.strasse}`}
                                    {d.spielstaette.ort && `, ${d.spielstaette.ort}`}
                                    {d.spielstaette.belag && ` · ${d.spielstaette.belag}`}
                                </span>
                            </p>
                        )}
                    </CardContent>
                </Card>

                <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
                    <Abschnitt
                        titel="Spielverlauf"
                        icon={ListChecks}
                        rechts={
                            <span className="hidden text-xs text-muted-foreground sm:inline">
                                Heim links · Gast rechts
                            </span>
                        }
                    >
                        {d.ereignisse.length === 0 ? (
                            <p className="text-sm text-muted-foreground">Keine Ereignisse im Bericht.</p>
                        ) : (
                            <ul className="divide-y">
                                {d.ereignisse.map((e, i) => <EreignisZeile key={i} e={e}/>)}
                            </ul>
                        )}
                    </Abschnitt>

                    <div className="space-y-4">
                        <Abschnitt titel="Gespann" icon={Users}>
                            <div className="space-y-1.5">
                                {d.gespann.map((p) => (
                                    <div key={p.rolle} className="flex gap-3 text-sm">
                                        <span className="w-10 shrink-0 text-xs leading-5 text-muted-foreground">{p.rolle}</span>
                                        <span className="min-w-0 break-words">
                                            {p.name}
                                            {p.verein && <span className="text-muted-foreground"> · {p.verein}</span>}
                                            {p.nicht_angetreten && (
                                                <Badge variant="destructive" className="ml-1.5">nicht angetreten</Badge>
                                            )}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </Abschnitt>

                        <Abschnitt titel="Schiedsrichterkosten laut DFBnet" icon={Euro}>
                            {hatKosten ? (
                                <>
                                    <Zeile label="Fahrtkosten Gespann">{formatEuro(d.kosten.fahrtkosten)}</Zeile>
                                    <Zeile label="SR-/SRA-Spesen Gespann">{formatEuro(d.kosten.spesen)}</Zeile>
                                    <Separator className="my-1"/>
                                    <Zeile label="Gesamt"><span className="font-medium">{formatEuro(kostenGesamt)}</span></Zeile>
                                    <p className="mt-2 text-xs text-muted-foreground">
                                        DFBnet führt nur die Summen des ganzen Gespanns – wer welchen Anteil hatte,
                                        steht nicht im Bericht.
                                    </p>
                                </>
                            ) : (
                                <p className="text-sm text-muted-foreground">Im Bericht sind keine Kosten eingetragen.</p>
                            )}
                        </Abschnitt>

                        <Abschnitt
                            titel="Dokumente"
                            icon={Paperclip}
                            rechts={<span className="text-xs text-muted-foreground">{bericht.dokumente.length}</span>}
                        >
                            {bericht.dokumente.length === 0 ? (
                                <p className="text-sm text-muted-foreground">Am Bericht hängen keine Dokumente.</p>
                            ) : (
                                <ul className="-my-3 divide-y">
                                    {bericht.dokumente.map((dok) => (
                                        <DokumentZeile key={dok.id} berichtId={bericht.id} dokument={dok}/>
                                    ))}
                                </ul>
                            )}
                        </Abschnitt>
                    </div>
                </div>

                <Abschnitt titel="Aufstellungen" icon={Shirt}>
                    <div className="grid gap-6 sm:grid-cols-2">
                        <AufstellungsSpalte titel={bericht.heim || d.heim} aufstellung={d.aufstellung.heim}/>
                        <AufstellungsSpalte titel={bericht.gast || d.gast} aufstellung={d.aufstellung.gast}/>
                    </div>
                </Abschnitt>

                <Abschnitt titel="Weitere Angaben" icon={ClipboardList}>
                    <div className="grid gap-x-8 gap-y-4 md:grid-cols-2">
                        <div>
                            {d.kontrollen.map((k) => (
                                <Zeile key={k.name} label={k.name}>
                                    {k.wert || '–'}
                                    {k.bemerkung && <span className="block text-xs text-muted-foreground">{k.bemerkung}</span>}
                                </Zeile>
                            ))}
                            <Zeile label="Besonders faires Verhalten">{d.fairplay ? 'ja' : 'nein'}</Zeile>
                            <Zeile label="Vorkommnisse">
                                {v.gemeldet ? (
                                    <span className="text-destructive">
                                        {[v.gewalt && 'Gewalt', v.diskriminierung && 'Diskriminierung'].filter(Boolean).join(', ') || 'gemeldet'}
                                        {v.spielabbruch && ' · Spielabbruch'}
                                    </span>
                                ) : 'keine'}
                            </Zeile>
                            {v.gemeldet && v.beschuldigte.length > 0 && (
                                <Zeile label="Beschuldigte">{v.beschuldigte.join(', ')}</Zeile>
                            )}
                            {v.gemeldet && v.geschaedigte.length > 0 && (
                                <Zeile label="Geschädigte">{v.geschaedigte.join(', ')}</Zeile>
                            )}
                        </div>
                        <div>
                            {(['heim', 'gast', 'schiedsrichter'] as const).map((wer) => {
                                const b = d.bestaetigung[wer];
                                const label = wer === 'heim' ? 'Bestätigt Heim' : wer === 'gast' ? 'Bestätigt Gast' : 'Freigabe SR';
                                return (
                                    <Zeile key={wer} label={label}>
                                        {b ? (
                                            <>
                                                {b.name}
                                                <span className="block text-xs text-muted-foreground">{zeitpunktText(b.zeit)}</span>
                                            </>
                                        ) : 'nein'}
                                    </Zeile>
                                );
                            })}
                        </div>
                    </div>
                    {d.bemerkungen && (
                        <div className="mt-4">
                            <p className="mb-1 text-xs tracking-wide text-muted-foreground uppercase">Sonstige Bemerkungen</p>
                            <p className="text-sm whitespace-pre-line break-words">{d.bemerkungen}</p>
                        </div>
                    )}
                </Abschnitt>

                <p className="text-xs text-muted-foreground">
                    Aus DFBnet gelesen am {new Date(bericht.scraped_at).toLocaleDateString('de-DE')}. Änderungen im Spielbericht
                    erscheinen hier beim nächsten Abruf.
                </p>
            </div>
        </AppShell>
    );
}
