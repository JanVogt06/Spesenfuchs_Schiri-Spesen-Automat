import {Calendar, Check, Download, FileArchive, Lock, Route, Table2, User} from 'lucide-react';

/*
 * Schaufenster der Landingpage: nachgebaute Ausschnitte der Anwendung mit
 * ausgedachten Beispieldaten. Vereine, Kilometer und Zaehler sind erfunden,
 * die Saetze stammen aus der TFV-Spesenordnung (Stand 01.07.2025). Gerechnet
 * wird hier nichts - das bleibt Sache des Backends, siehe
 * generator/spesen_calculator.py.
 *
 * Alles hier ist Bild, nicht Inhalt: die Bausteine sind fuer Screenreader
 * ausgeblendet, beschrieben wird die Funktion jeweils im Text daneben.
 */

/** Pulsierender Punkt, wie ein Live-Signal */
export function Puls({className = 'size-2'}: { className?: string }) {
    return (
        <span className={`relative grid shrink-0 place-items-center ${className}`}>
            <span className="spesen-puls absolute inset-0 rounded-full bg-flutlicht"/>
            <span className="size-full rounded-full bg-flutlicht"/>
        </span>
    );
}

/*
 * Das Gespann der Beispielabrechnung. Summe = Satz + km x 0,30 EUR, so wie
 * das Formular sie je Person ausweist.
 */
const GESPANN = [
    {rolle: 'SR', satz: '50,00', km: '42', summe: '62,60'},
    {rolle: 'SRA 1', satz: '40,00', km: '38', summe: '51,40'},
    {rolle: 'SRA 2', satz: '40,00', km: '55', summe: '56,50'},
];

/*
 * Spalten der Abrechnung. Schmal (die Karte am Handy, 320 px) ruecken sie
 * enger zusammen, damit kein Betrag umbricht.
 */
const SPALTEN = 'grid grid-cols-[2.75rem_minmax(0,1fr)_auto_3.75rem] gap-x-2 px-2.5 ' +
    'min-[400px]:grid-cols-[3.25rem_minmax(0,1fr)_auto_4.75rem] min-[400px]:gap-x-3 min-[400px]:px-3';

function Dateiknopf({label}: { label: string }) {
    return (
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.04] px-2.5 py-1 text-xs font-medium text-white/85">
            <Download className="size-3.5"/>
            {label}
        </span>
    );
}

/**
 * Die Beispielabrechnung: ein Spiel mit Gespann, Saetzen, Kilometern und
 * Summen. Die Flaeche ist bewusst deckend - durchscheinende Karten dahinter
 * wirkten wie ein Darstellungsfehler.
 */
export function Abrechnungskarte() {
    return (
        <div
            aria-hidden
            className="relative overflow-hidden rounded-2xl border border-white/15 bg-[oklch(0.215_0.03_158)] p-4 text-white shadow-2xl shadow-black/60 sm:p-5"
        >
            <div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-flutlicht/70 to-transparent"/>

            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="text-sm leading-snug font-semibold">SV Grün-Weiß – FC Kreisstadt</p>
                    <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-white/55">
                        <span className="inline-flex items-center gap-1.5">
                            <Calendar className="size-3.5"/>
                            Sa · 22.11. · 13:00 Uhr
                        </span>
                        <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] font-medium text-white/80">
                            Verbandsliga · Herren
                        </span>
                    </p>
                </div>
                <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-flutlicht/15 px-2 py-0.5 text-xs font-medium text-flutlicht">
                    <Puls className="size-1.5"/>
                    Fertig
                </span>
            </div>

            <div className="mt-4 rounded-xl border border-white/10 bg-black/20 text-sm">
                <div className={`${SPALTEN} border-b border-white/10 py-2 text-[10px] font-medium tracking-wider text-white/40 uppercase`}>
                    <span>Rolle</span>
                    <span>Satz</span>
                    <span>Fahrt</span>
                    <span className="text-right">Summe</span>
                </div>
                {GESPANN.map((zeile) => (
                    <div
                        key={zeile.rolle}
                        className={`${SPALTEN} items-center py-1.5 tabular-nums whitespace-nowrap`}
                    >
                        <span className="text-white/60">{zeile.rolle}</span>
                        <span className="font-medium text-flutlicht">{zeile.satz} €</span>
                        {/* Die Kilometer traegt man selbst ein - deshalb wie ein Eingabefeld */}
                        <span className="rounded-md border border-dashed border-white/25 px-1.5 py-px text-xs text-white/80">
                            {zeile.km} km
                        </span>
                        <span className="text-right text-white/85">{zeile.summe} €</span>
                    </div>
                ))}
                <div className="mt-1 flex items-center justify-between border-t border-white/10 px-2.5 py-2 min-[400px]:px-3">
                    <span className="text-white/55">Gesamt</span>
                    <span className="font-semibold tabular-nums">170,50 €</span>
                </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
                <Dateiknopf label="DOCX"/>
                <Dateiknopf label="PDF"/>
                <span className="ml-auto text-[11px] text-white/45">km von dir · Rest aus DFBnet</span>
            </div>
        </div>
    );
}

type Stand = 'fertig' | 'tabelle' | 'km';

const ANSETZUNGEN: { tag: string; paarung: string; klasse: string; stand: Stand }[] = [
    {tag: 'Sa 22.11.', paarung: 'SV Grün-Weiß – FC Kreisstadt', klasse: 'Verbandsliga', stand: 'fertig'},
    {tag: 'Mi 26.11.', paarung: 'TSV Musterdorf – SV Grün-Weiß', klasse: 'Landespokal', stand: 'tabelle'},
    {tag: 'So 30.11.', paarung: 'SG Blau-Gelb – FC Beispieltal', klasse: 'Landesklasse', stand: 'km'},
    {tag: 'Sa 06.12.', paarung: 'SV Talblick – FC Kreisstadt II', klasse: 'Kreisoberliga', stand: 'fertig'},
];

function Standanzeige({stand}: { stand: Stand }) {
    if (stand === 'tabelle') {
        return (
            <span className="inline-flex items-center gap-1 rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-white/75">
                <Table2 className="size-3"/>
                Satz aus Tabelle
            </span>
        );
    }
    if (stand === 'km') {
        return (
            <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-white/25 px-2 py-0.5 text-[11px] text-white/60">
                km offen
            </span>
        );
    }
    return (
        <span className="inline-flex items-center gap-1 rounded-full bg-flutlicht/15 px-2 py-0.5 text-[11px] text-flutlicht">
            <Check className="size-3"/>
            Fertig
        </span>
    );
}

/** Das Fenster "Meine Spiele" hinter der Beispielabrechnung */
export function Spieleliste() {
    return (
        <div
            aria-hidden
            className="overflow-hidden rounded-2xl border border-white/10 bg-[oklch(0.19_0.028_158)] text-white shadow-2xl shadow-black/50"
        >
            <div className="flex items-center gap-3 border-b border-white/10 px-4 py-2.5">
                <span className="flex gap-1.5">
                    <span className="size-2.5 rounded-full bg-white/15"/>
                    <span className="size-2.5 rounded-full bg-white/15"/>
                    <span className="size-2.5 rounded-full bg-white/15"/>
                </span>
                <span className="text-xs font-medium text-white/70">Meine Spiele</span>
                <span className="ml-auto flex items-center gap-1.5 text-[11px] text-white/50">
                    <Puls className="size-1.5"/>
                    Abruf heute 03:00
                </span>
            </div>
            <div className="divide-y divide-white/[0.06]">
                {ANSETZUNGEN.map((spiel) => (
                    <div key={spiel.tag} className="flex items-center gap-3 px-4 py-2.5">
                        <span className="w-16 shrink-0 text-[11px] text-white/45 tabular-nums">{spiel.tag}</span>
                        <div className="min-w-0 flex-1">
                            <p className="truncate text-xs font-medium text-white/85">{spiel.paarung}</p>
                            <p className="text-[11px] text-white/40">{spiel.klasse}</p>
                        </div>
                        <Standanzeige stand={spiel.stand}/>
                    </div>
                ))}
            </div>
        </div>
    );
}

/** Stecknadel mit der Spitze auf (x, y) */
function Nadel({x, y, className}: { x: number; y: number; className: string }) {
    return (
        <g transform={`translate(${x} ${y})`}>
            <path d="M0 0 C -1.6 -4.2 -6 -6.6 -6 -11 A 6 6 0 1 1 6 -11 C 6 -6.6 1.6 -4.2 0 0 Z" className={className}/>
            <circle cx="0" cy="-11" r="2.2" className="fill-white"/>
        </g>
    );
}

/**
 * Eine gezeichnete Anfahrtskarte: Strassen, ein Fluss, drei Anschriften des
 * Gespanns und die Spielstaette. Keine echte Gegend - nur das Bild, das die
 * Karte in der Anwendung liefert.
 */
export function Anfahrtskarte({dunkel = false, beschriftet = true, className}: {
    dunkel?: boolean;
    beschriftet?: boolean;
    className?: string;
}) {
    const strasse = dunkel ? 'stroke-white/[0.13]' : 'stroke-foreground/[0.11]';
    const fluss = dunkel ? 'stroke-sky-300/20' : 'stroke-sky-500/25';
    const weg = dunkel ? 'stroke-flutlicht/80' : 'stroke-primary/80';
    const haupt = dunkel ? 'fill-flutlicht' : 'fill-primary';
    const neben = dunkel ? 'fill-white/70' : 'fill-foreground/55';
    const schrift = dunkel ? 'fill-white/75 stroke-nacht' : 'fill-foreground/70 stroke-card';

    return (
        <svg viewBox="0 0 240 140" fill="none" aria-hidden className={className}>
            <rect x="150" y="8" width="80" height="44" rx="10" className={dunkel ? 'fill-white/[0.03]' : 'fill-foreground/[0.035]'}/>
            <rect x="6" y="54" width="46" height="30" rx="8" className={dunkel ? 'fill-white/[0.03]' : 'fill-foreground/[0.035]'}/>
            <path d="M-5 38 C 40 52, 72 24, 120 34 S 200 20, 245 28" strokeWidth="7" strokeLinecap="round" className={fluss}/>
            <path d="M-5 106 C 50 92, 92 120, 140 100 S 206 72, 245 80" strokeWidth="4.5" className={strasse}/>
            <path d="M74 -5 C 80 40, 66 82, 94 145" strokeWidth="3" className={strasse}/>
            <path d="M184 -5 L 198 145" strokeWidth="2.5" className={strasse}/>
            <path d="M120 60 L 245 52" strokeWidth="2" className={strasse}/>

            {/* Wege zur Spielstaette */}
            <g strokeWidth="1.6" strokeDasharray="3 4" strokeLinecap="round" className={weg}>
                <path d="M40 116 C 70 104, 104 96, 140 80"/>
                <path d="M58 36 C 86 46, 116 58, 144 70"/>
                <path d="M214 118 C 200 102, 182 90, 164 82"/>
            </g>

            {/* Spielstaette als kleines Feld */}
            <g transform="translate(140 66)">
                <rect width="26" height="17" rx="2.5" className={haupt}/>
                <line x1="13" y1="1.5" x2="13" y2="15.5" strokeWidth="1" className="stroke-white/80"/>
                <circle cx="13" cy="8.5" r="3.4" strokeWidth="1" className="stroke-white/80"/>
            </g>

            <Nadel x={40} y={116} className={haupt}/>
            <Nadel x={58} y={36} className={neben}/>
            <Nadel x={214} y={118} className={neben}/>

            {beschriftet && (
                <g fontSize="9" fontWeight="600" strokeWidth="3" strokeLinejoin="round" paintOrder="stroke" className={schrift}>
                    <text x="40" y="131" textAnchor="middle">SR</text>
                    <text x="68" y="28">SRA 1</text>
                    <text x="214" y="131" textAnchor="middle">SRA 2</text>
                    <text x="153" y="97" textAnchor="middle">Spielstätte</text>
                </g>
            )}
        </svg>
    );
}

/** Kleiner Anhaenger zur Buehne im Hero: die Karte zur Anfahrt */
export function Anfahrtschip() {
    return (
        <div
            aria-hidden
            className="overflow-hidden rounded-2xl border border-white/15 bg-[oklch(0.2_0.03_158)] text-white shadow-2xl shadow-black/60"
        >
            <Anfahrtskarte dunkel beschriftet={false} className="block h-auto w-full bg-[oklch(0.17_0.025_158)]"/>
            {/* Rechtsbuendig: links schiebt sich im Hero die Abrechnung darueber */}
            <div className="flex items-center justify-end gap-2 border-t border-white/10 px-3 py-2 text-[11px]">
                <Route className="size-3.5 text-flutlicht"/>
                <span className="text-white/70">Anfahrt SR</span>
                <span className="font-medium text-white tabular-nums">42 km</span>
            </div>
        </div>
    );
}

/**
 * Uhr auf drei Uhr nachts - die Zeit, zu der der Lauf fuer alle Nutzer
 * startet. Der Stundenzeiger ist kurz und kraeftig, der Minutenzeiger lang
 * und duenn, sonst liesse sich die Uhr genauso als Viertel nach zwoelf lesen.
 */
export function Nachtuhr({className = 'size-24 sm:size-28'}: { className?: string }) {
    return (
        <svg viewBox="0 0 100 100" className={className} fill="none" aria-hidden>
            <circle cx="50" cy="50" r="46" strokeWidth="1" className="stroke-white/15"/>
            {Array.from({length: 12}, (_, stunde) => {
                const winkel = (stunde * Math.PI) / 6;
                const innen = stunde % 3 === 0 ? 33 : 36;
                return (
                    <line
                        key={stunde}
                        x1={50 + 40 * Math.sin(winkel)}
                        y1={50 - 40 * Math.cos(winkel)}
                        x2={50 + innen * Math.sin(winkel)}
                        y2={50 - innen * Math.cos(winkel)}
                        strokeWidth={stunde % 3 === 0 ? 2 : 1.2}
                        strokeLinecap="round"
                        className={stunde === 3 ? 'stroke-flutlicht' : 'stroke-white/30'}
                    />
                );
            })}
            {/* Minutenzeiger auf 12, Stundenzeiger auf 3 */}
            <line x1="50" y1="50" x2="50" y2="17" strokeWidth="2" strokeLinecap="round" className="stroke-white/75"/>
            <line x1="50" y1="50" x2="70" y2="50" strokeWidth="4.5" strokeLinecap="round" className="stroke-flutlicht"/>
            <circle cx="50" cy="50" r="3.5" className="fill-flutlicht stroke-none"/>
        </svg>
    );
}

const EINSAETZE = [
    {rolle: 'SR', zahl: 18},
    {rolle: 'SRA 1', zahl: 7},
    {rolle: 'SRA 2', zahl: 4},
];

function Kartenzaehler({farbe, zahl}: { farbe: string; zahl: number }) {
    return (
        <span className="inline-flex items-center gap-1.5">
            <span className={`h-3.5 w-2.5 rotate-[8deg] rounded-[2px] shadow-sm shadow-black/40 ${farbe}`}/>
            <span className="font-medium tabular-nums">{zahl}</span>
        </span>
    );
}

/**
 * Die Saison als Mini-Tafel: Einsatzbilanz nach Rolle, Karten ueber alle
 * geleiteten Spiele, Lehrabende und Leistungspruefung. Die Balken wachsen
 * beim Einblenden (siehe .spesen-balken), ohne Bewegung stehen sie sofort.
 */
export function Saisontafel() {
    const hoechstens = Math.max(...EINSAETZE.map((eintrag) => eintrag.zahl));

    return (
        <div aria-hidden className="rounded-xl border border-white/10 bg-black/25 p-4 text-white">
            <div className="flex items-center justify-between text-[11px] text-white/45">
                <span className="font-medium tracking-wider uppercase">Saison 25/26</span>
                <span>Beispiel</span>
            </div>

            <div className="mt-3 grid gap-2.5">
                {EINSAETZE.map((eintrag, index) => (
                    <div key={eintrag.rolle} className="grid grid-cols-[2.75rem_1fr_1.75rem] items-center gap-3 text-xs">
                        <span className="text-white/60">{eintrag.rolle}</span>
                        <span className="h-2 overflow-hidden rounded-full bg-white/10">
                            <span
                                className="spesen-balken block h-full rounded-full bg-flutlicht"
                                style={{width: `${(eintrag.zahl / hoechstens) * 100}%`, transitionDelay: `${200 + index * 120}ms`}}
                            />
                        </span>
                        <span className="text-right font-medium tabular-nums">{eintrag.zahl}</span>
                    </div>
                ))}
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-white/10 pt-3 text-xs">
                <Kartenzaehler farbe="bg-yellow-400" zahl={41}/>
                <Kartenzaehler farbe="bg-gradient-to-br from-yellow-400 from-50% to-red-500 to-50%" zahl={3}/>
                <Kartenzaehler farbe="bg-red-500" zahl={2}/>
                <span className="ml-auto text-white/55">Lehrabende 3 · Leistungsprüfung ✓</span>
            </div>
        </div>
    );
}

/*
 * Die hellen Belege stehen in Kacheln von fester Hoehe, die als @container
 * ausgezeichnet sind (siehe Funktionskachel in Landing.tsx). Wird eine Kachel
 * schmaler als 13rem - am Handy mit 320 px -, ruecken die Belege per zoom ein
 * Stueck zusammen, statt umzubrechen und unten aus der Kachel zu laufen.
 */
const SCHMAL = '@max-[13rem]:[zoom:0.85]';

/** Ein Pokalspiel und wie der Satz dazu zustande kommt */
export function Ligenauszug() {
    return (
        <div aria-hidden className={`w-full max-w-[20rem] rounded-xl border bg-card p-3 text-xs shadow-sm ${SCHMAL}`}>
            <div className="flex items-center justify-between gap-3 text-muted-foreground">
                <span className="font-medium text-foreground">Landespokal</span>
                <span className="tabular-nums">Mi 26.11.</span>
            </div>
            <div className="mt-2 grid gap-0.5 whitespace-nowrap">
                <div className="flex items-center justify-between gap-2 rounded-md px-2 py-[3px]">
                    <span>TSV Musterdorf</span>
                    <span className="text-muted-foreground">Landesklasse</span>
                </div>
                <div className="flex items-center justify-between gap-2 rounded-md bg-primary/10 px-2 py-[3px]">
                    <span className="font-medium">SV Grün-Weiß</span>
                    <span className="font-medium text-primary">Thüringenliga</span>
                </div>
            </div>
            <div className="mt-2 border-t pt-1.5">
                <p className="text-muted-foreground">höchste Klasse zählt</p>
                <p className="flex items-center justify-between gap-2 whitespace-nowrap">
                    <span className="text-muted-foreground">SR / SRA</span>
                    <span className="font-semibold text-primary tabular-nums">50,00 € / 40,00 €</span>
                </p>
            </div>
        </div>
    );
}

function Stammzeile({name, children}: { name: string; children: React.ReactNode }) {
    return (
        <div className="flex items-center justify-between gap-3">
            <span className="text-muted-foreground">{name}</span>
            {children}
        </div>
    );
}

/** Ausschnitt aus dem Reiter "Stammdaten" - ohne Namen, die Angaben verdeckt */
export function Stammdatenauszug() {
    return (
        <div aria-hidden className={`w-full max-w-[20rem] rounded-xl border bg-card p-3 text-xs shadow-sm ${SCHMAL}`}>
            <div className="flex items-center gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground">
                    <User className="size-4"/>
                </span>
                <div className="grid min-w-0 flex-1 gap-1.5">
                    <span className="h-2 w-full max-w-24 rounded-full bg-foreground/15"/>
                    <span className="h-2 w-2/3 max-w-16 rounded-full bg-foreground/10"/>
                </div>
                <span className="inline-flex shrink-0 items-center gap-1 text-muted-foreground">
                    <Lock className="size-3"/>
                    verschlüsselt
                </span>
            </div>
            <div className="mt-3 grid gap-1.5">
                <Stammzeile name="Verein">
                    <span>SV Grün-Weiß</span>
                </Stammzeile>
                <Stammzeile name="Anschrift">
                    <span className="tracking-widest text-muted-foreground">•••• ••••</span>
                </Stammzeile>
                <Stammzeile name="QMax">
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 font-medium text-primary">Landesklasse</span>
                </Stammzeile>
            </div>
        </div>
    );
}

function Blatt({endung, vorne}: { endung: string; vorne?: boolean }) {
    return (
        <div
            className={`relative h-[5.5rem] w-16 rounded-md border bg-card p-2 shadow-sm ${
                vorne ? '-ml-5 translate-y-1 rotate-[5deg] shadow-md' : '-rotate-[4deg]'
            }`}
        >
            <div className="grid gap-1">
                <span className="h-1 w-8 rounded-full bg-foreground/20"/>
                <span className="h-1 w-10 rounded-full bg-foreground/10"/>
                <span className="h-1 w-9 rounded-full bg-foreground/10"/>
                <span className="h-1 w-6 rounded-full bg-foreground/10"/>
            </div>
            <span
                className={`absolute bottom-1.5 left-1.5 rounded px-1 py-0.5 text-center text-[9px] font-semibold tracking-wide ${
                    vorne ? 'right-1.5 bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                }`}
            >
                {endung}
            </span>
        </div>
    );
}

/**
 * Word und PDF je Spiel, alles zusammen als ZIP. Wird die Kachel zu schmal,
 * rutscht das ZIP unter die Blaetter, statt in zwei Zeilen umzubrechen.
 */
export function Dokumente() {
    return (
        <div aria-hidden className="flex w-full flex-wrap items-center justify-center gap-x-5 gap-y-3">
            <div className="flex items-end">
                <Blatt endung="DOCX"/>
                <Blatt endung="PDF" vorne/>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-lg border bg-card px-2.5 py-1.5 text-xs font-medium whitespace-nowrap shadow-sm">
                <FileArchive className="size-3.5 text-primary"/>
                Alle als ZIP
            </span>
        </div>
    );
}
