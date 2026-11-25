import type {CSSProperties, ReactNode} from 'react';
import {
    ArrowDown,
    ArrowLeftRight,
    Car,
    ChartColumn,
    CheckCircle2,
    ClipboardCheck,
    ClipboardList,
    CalendarDays,
    Ellipsis,
    Euro,
    FileText,
    Goal,
    Hash,
    LayoutDashboard,
    Link2,
    Lock,
    MapPin,
    MapPinned,
    Paperclip,
    Phone,
    RefreshCw,
    Route,
    Search,
    ShieldCheck,
    Smartphone,
    Trophy,
    Users,
} from 'lucide-react';
import {ADRESSE, Beitrag, Etikett, Folie, Kachel, Leucht, STORY, Titel} from './Rahmen';
import {Beobachtungstafel, Karte} from './Update';

/*
 * Instagram post for everything since the last post (the update story of
 * November): a recap of that story, then the match list, mileage
 * suggestions with carpools, the statistics, match reports and the smaller
 * things. Eight slides in the shared frame, reachable at
 * /instagram-halbzeit.html with ?s=1 to ?s=8; 3:4 by default, &f=story for 9:16.
 *
 * The excerpts are recreated, the data made up - like on the landing page.
 */

const ANZAHL = 8;

/** Small grey caption above a block, like the section headers in the app */
function Unterzeile({icon: Icon, children}: { icon: typeof Route; children: ReactNode }) {
    return (
        <p className="flex items-center gap-1.5 text-[11.5px] font-medium text-white/55">
            <Icon className="size-3.5"/>
            {children}
        </p>
    );
}

function Knopf({children}: { children: ReactNode }) {
    return (
        <span className="shrink-0 rounded-md border border-white/15 bg-white/[0.06] px-2.5 py-1 text-[11px] font-medium text-white/85">
            {children}
        </span>
    );
}

function Haken({children}: { children: ReactNode }) {
    return (
        <li className="flex items-center gap-2">
            <CheckCircle2 className="size-4 shrink-0 text-flutlicht"/>
            {children}
        </li>
    );
}

/* ---------- Mileage suggestions ---------- */

/** The suggestions above the travel cost fields: alone, picking up, meeting point */
function Fahrtvorschlaege() {
    return (
        <Karte>
            <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-2.5">
                <span className="flex items-center gap-2 text-[13px]">
                    <Car className="size-4 text-white/55"/>
                    <span className="font-semibold">Fahrtkosten</span>
                    <span className="text-white/50">Sa 29.11. · Landesklasse</span>
                </span>
                <span className="text-[11px] text-white/45">Beispiel</span>
            </div>

            <div className="grid gap-2 p-3.5">
                <Unterzeile icon={Route}>Vorschlag, jeweils Hin- und Rückfahrt</Unterzeile>

                <div className="flex items-center justify-between gap-3 rounded-lg bg-white/[0.05] px-3 py-2">
                    <div className="min-w-0 text-[12.5px]">
                        <p className="flex items-center gap-1.5 font-medium">
                            <Car className="size-3.5 shrink-0 text-white/50"/>
                            Jeder fährt allein
                            <span className="font-normal text-white/50">· 236 km</span>
                        </p>
                        <p className="text-[11px] text-white/50">SR (du) 92 km · SRA 1 78 km · SRA 2 66 km</p>
                    </div>
                    <Knopf>Übernehmen</Knopf>
                </div>

                <div className="flex items-center justify-between gap-3 rounded-lg bg-flutlicht/[0.07] px-3 py-2 ring-1 ring-flutlicht/30">
                    <div className="min-w-0 text-[12.5px]">
                        <p className="flex flex-wrap items-center gap-x-1.5 font-medium">
                            <Users className="size-3.5 shrink-0 text-flutlicht"/>
                            Fahrgemeinschaft
                            <span className="font-normal text-white/50">· 148 km</span>
                            <span className="text-[11px] font-normal text-flutlicht">spart 88 km</span>
                        </p>
                        <p className="text-[11px] text-white/50">SR (du) fährt und holt SRA 1 und SRA 2 ab (148 km)</p>
                    </div>
                    <Knopf>Übernehmen</Knopf>
                </div>

                <div className="flex items-center justify-between gap-3 rounded-lg bg-flutlicht/[0.07] px-3 py-2 ring-1 ring-flutlicht/30">
                    <div className="min-w-0 text-[12.5px]">
                        <p className="flex flex-wrap items-center gap-x-1.5 font-medium">
                            <Users className="size-3.5 shrink-0 text-flutlicht"/>
                            Fahrgemeinschaft
                            <span className="font-normal text-white/50">· 160 km</span>
                            <span className="text-[11px] font-normal text-flutlicht">spart 76 km</span>
                        </p>
                        <p className="text-[11px] leading-snug text-white/50">
                            SR (du) fährt (120 km), SRA 1 (22 km) und SRA 2 (18 km) kommen zum Treffpunkt etwa bei Kranichfeld{' '}
                            <span className="inline-flex items-center gap-0.5 text-flutlicht">
                                <MapPin className="size-3"/>
                                Karte
                            </span>
                        </p>
                    </div>
                    <Knopf>Übernehmen</Knopf>
                </div>
            </div>
        </Karte>
    );
}

/* ---------- Statistics ---------- */

const SPESEN = 'oklch(0.68 0.14 155)';
const FAHRT = 'oklch(0.66 0.11 255)';
const SCHRAFFUR = `repeating-linear-gradient(45deg, ${FAHRT} 0 2px, transparent 2px 5px)`;

const MONATE = [
    {monat: 'August', spesen: 290, fahrt: 140.4, geschaetzt: 0, summe: '430,40 €'},
    {monat: 'September', spesen: 340, fahrt: 158.6, geschaetzt: 0, summe: '498,60 €'},
    {monat: 'Oktober', spesen: 352, fahrt: 164.5, geschaetzt: 0, summe: '516,50 €'},
    {monat: 'November', spesen: 302, fahrt: 0, geschaetzt: 148.8, summe: '≈ 450,80 €'},
];
const MAXIMUM = 516.5;

function Balken({wert, stil, erster, letzter}: { wert: number; stil: CSSProperties; erster: boolean; letzter: boolean }) {
    return (
        <span
            className={`h-full ${erster ? 'rounded-l' : ''} ${letzter ? 'rounded-r' : ''}`}
            style={{...stil, width: `${(wert / MAXIMUM) * 100}%`}}
        />
    );
}

/** The "Spesen & Fahrtkosten" card of the Statistik tab */
function Statistiktafel({monate = true}: { monate?: boolean }) {
    const zahlen = [
        {label: 'Spesen', wert: '1.284,00 €', zusatz: '26 Spiele'},
        {label: 'Fahrtkosten', wert: '≈ 612,30 €', zusatz: '148,80 € geschätzt'},
        {label: 'Zusammen', wert: '≈ 1.896,30 €', zusatz: 'Ø 72,93 € je Spiel'},
    ];
    return (
        <Karte>
            <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-2.5">
                <span className="flex items-center gap-2 text-[13px]">
                    <Euro className="size-4 text-white/55"/>
                    <span className="font-semibold">Spesen & Fahrtkosten</span>
                    <span className="text-white/50">26/27</span>
                </span>
                <span className="text-[11px] text-white/45">Beispiel</span>
            </div>

            <div className="grid gap-3.5 p-4">
                <div className="grid grid-cols-3 gap-3">
                    {zahlen.map((zahl) => (
                        <div key={zahl.label} className="min-w-0">
                            <p className="text-[11px] text-white/55">{zahl.label}</p>
                            <p className="mt-0.5 truncate text-[18px] leading-tight font-semibold tabular-nums">{zahl.wert}</p>
                            <p className="truncate text-[10.5px] text-white/45">{zahl.zusatz}</p>
                        </div>
                    ))}
                </div>

                {monate && (
                    <div className="grid gap-2">
                        <ul className="flex flex-wrap gap-x-4 text-[10.5px] text-white/55">
                            {[
                                {name: 'Spesen', stil: {background: SPESEN}},
                                {name: 'Fahrtkosten', stil: {background: FAHRT}},
                                {name: 'Fahrtkosten geschätzt', stil: {background: SCHRAFFUR, boxShadow: `inset 0 0 0 1px ${FAHRT}`}},
                            ].map((eintrag) => (
                                <li key={eintrag.name} className="flex items-center gap-1.5">
                                    <span className="size-2.5 rounded-sm" style={eintrag.stil}/>
                                    {eintrag.name}
                                </li>
                            ))}
                        </ul>
                        <ul className="grid gap-1.5">
                            {MONATE.map((m) => (
                                <li key={m.monat} className="grid grid-cols-[4.2rem_1fr_5.2rem] items-center gap-2.5">
                                    <span className="text-[11px] text-white/55">{m.monat}</span>
                                    <span className="flex h-3 gap-[2px]">
                                        <Balken wert={m.spesen} stil={{background: SPESEN}} erster letzter={false}/>
                                        {m.fahrt > 0 && <Balken wert={m.fahrt} stil={{background: FAHRT}} erster={false} letzter/>}
                                        {m.geschaetzt > 0 && (
                                            <Balken
                                                wert={m.geschaetzt}
                                                stil={{background: SCHRAFFUR, boxShadow: `inset 0 0 0 1px ${FAHRT}`}}
                                                erster={false}
                                                letzter
                                            />
                                        )}
                                    </span>
                                    <span className="text-right font-mono text-[11px] tabular-nums">{m.summe}</span>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>
        </Karte>
    );
}

// Made-up venues on a made-up map - roughly the shape of a state, no real coordinates
const ORTE: [number, number][] = [
    [62, 38], [88, 30], [118, 44], [140, 36], [166, 52], [74, 62], [102, 66], [128, 70], [152, 78],
    [184, 70], [58, 86], [92, 92], [118, 98], [146, 104], [174, 96], [206, 88], [84, 112], [132, 120],
];

/** The venue map: every venue where one has already officiated */
function Spielstaetten() {
    return (
        <Karte className="grid grid-cols-[1fr_9.5rem]">
            <svg viewBox="0 0 250 140" preserveAspectRatio="xMidYMid slice" className="h-[112px] w-full bg-[oklch(0.19_0.025_158)]">
                <path
                    d="M30 52 C 48 18, 96 10, 132 20 S 206 30, 226 58 S 214 118, 176 128 S 94 138, 60 124 S 16 86, 30 52 Z"
                    className="fill-white/[0.04] stroke-white/20"
                    strokeWidth="1"
                    strokeDasharray="3 3"
                />
                <path d="M40 70 L 110 60 L 160 88 L 220 74" className="fill-none stroke-white/10" strokeWidth="2"/>
                <path d="M70 30 L 100 96 L 120 130" className="fill-none stroke-white/10" strokeWidth="2"/>
                {ORTE.map(([x, y], index) => (
                    <circle key={index} cx={x} cy={y} r={index % 5 === 0 ? 5 : 4} fill={SPESEN} stroke="oklch(0.19 0.025 158)" strokeWidth="1.5"/>
                ))}
            </svg>
            <div className="flex flex-col justify-center gap-1 border-l border-white/10 px-3.5 py-3">
                <Unterzeile icon={MapPinned}>Spielstätten</Unterzeile>
                <p className="font-mono text-[24px] leading-tight font-semibold">18</p>
                <p className="text-[11px] leading-snug text-white/55">Orte, an denen du schon gepfiffen hast – je Saison oder alle.</p>
            </div>
        </Karte>
    );
}

/* ---------- Match list ---------- */

const SPIELE = [
    {monat: 'November 2026'},
    {tag: 'Sa', datum: '29.11.', zeit: '14:00', klasse: 'Landesklasse', heim: 'SV Grün-Weiß Musterhausen', gast: 'FC Beispielstadt', rolle: 'SR'},
    {monat: 'Dezember 2026'},
    {tag: 'Sa', datum: '06.12.', zeit: '13:30', klasse: 'Thüringenliga', heim: 'VfB Talheim', gast: 'SG Am Bergsee', rolle: 'SRA 1'},
    {tag: 'So', datum: '07.12.', zeit: '10:30', klasse: 'A-Junioren', heim: 'FSV Lindenau', gast: 'SpVgg Waldfeld', rolle: 'SR'},
];

const TABS = [
    {label: 'Übersicht', icon: LayoutDashboard},
    {label: 'Spiele', icon: CalendarDays},
    {label: 'Saison', icon: Trophy},
    {label: 'Statistik', icon: ChartColumn},
    {label: 'Noten', icon: ClipboardCheck},
    {label: 'Mehr', icon: Ellipsis},
];

/** The tab bar of the phone, with the new main tabs */
function Tableiste({aktiv}: { aktiv: number }) {
    return (
        <div className="flex rounded-full border border-white/15 bg-[oklch(0.24_0.03_158)] p-1 shadow-2xl shadow-black/60">
            {TABS.map((tab, index) => (
                <span
                    key={tab.label}
                    className={`flex h-12 flex-1 flex-col items-center justify-center gap-0.5 rounded-full text-[9.5px] font-medium ${
                        index === aktiv ? 'bg-flutlicht/15 text-flutlicht' : 'text-white/55'
                    }`}
                >
                    <tab.icon className="size-[18px]"/>
                    {tab.label}
                </span>
            ))}
        </div>
    );
}

/** The "Spiele" tab: header with refresh, upcoming/past, search, months */
function Spieleliste() {
    return (
        <Karte>
            <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-2.5">
                <div>
                    <p className="text-[14px] font-semibold">Spiele</p>
                    <p className="text-[10.5px] text-white/45">DFBnet gelesen heute, 03:12 Uhr</p>
                </div>
                <span className="flex items-center gap-1.5 rounded-md bg-flutlicht px-2.5 py-1.5 text-[11.5px] font-semibold text-nacht">
                    <RefreshCw className="size-3.5"/>
                    Aktualisieren
                </span>
            </div>

            <div className="grid gap-2.5 p-3.5">
                <div className="flex items-center gap-2">
                    <span className="inline-flex shrink-0 rounded-lg border border-white/10 bg-black/20 p-0.5 text-[11.5px] font-medium">
                        <span className="rounded-md bg-flutlicht/15 px-2.5 py-1 text-flutlicht">Kommend <span className="opacity-70">3</span></span>
                        <span className="px-2.5 py-1 text-white/50">Vergangen <span className="opacity-70">26</span></span>
                    </span>
                    <span className="flex min-w-0 flex-1 items-center gap-1.5 rounded-lg border border-white/10 bg-black/20 px-2.5 py-1 text-[11.5px] text-white/40">
                        <Search className="size-3.5 shrink-0"/>
                        <span className="truncate">Verein, Spielklasse oder Spielstätte</span>
                    </span>
                </div>

                <div className="grid gap-1.5">
                    {SPIELE.map((spiel) => 'monat' in spiel ? (
                        <p key={spiel.monat} className="mt-1 text-[10.5px] font-medium tracking-wider text-white/45 uppercase">{spiel.monat}</p>
                    ) : (
                        <div key={spiel.datum} className="grid grid-cols-[3.2rem_1fr_auto] items-center gap-3 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2">
                            <div className="text-center leading-tight">
                                <p className="text-[10px] text-white/50">{spiel.tag}</p>
                                <p className="font-mono text-[13px] font-semibold">{spiel.datum}</p>
                            </div>
                            <div className="min-w-0 text-[12px]">
                                <p className="truncate font-medium">{spiel.heim} – {spiel.gast}</p>
                                <p className="truncate text-[10.5px] text-white/50">{spiel.zeit} Uhr · {spiel.klasse}</p>
                            </div>
                            <span className="rounded-md bg-white/[0.07] px-2 py-0.5 text-[10.5px] font-medium text-white/70">{spiel.rolle}</span>
                        </div>
                    ))}
                </div>
            </div>
        </Karte>
    );
}

/* ---------- Match report ---------- */

const EREIGNISSE = [
    {minute: "12'", typ: 'tor', person: 'M. Keller (9)', text: 'Tor', gast: false},
    {minute: "38'", typ: 'gelb', person: 'T. Wagner (5)', text: 'Gelbe Karte · Foulspiel', gast: true},
    {minute: "61'", typ: 'wechsel', person: 'L. Braun (14) für P. Otto (7)', text: 'Wechsel', gast: false},
    {minute: "74'", typ: 'tor', person: 'J. Fischer (11)', text: 'Tor', gast: true},
    {minute: "89'", typ: 'gelbrot', person: 'T. Wagner (5)', text: 'Gelb-Rote Karte · Foulspiel', gast: true},
];

function Symbol({typ}: { typ: string }) {
    if (typ === 'gelb') return <span className="inline-block h-4 w-3 rounded-[2px] bg-yellow-400"/>;
    if (typ === 'gelbrot') {
        return (
            <span className="inline-block h-4 w-3 overflow-hidden rounded-[2px]">
                <span className="block h-1/2 bg-yellow-400"/>
                <span className="block h-1/2 bg-red-600"/>
            </span>
        );
    }
    if (typ === 'wechsel') return <ArrowLeftRight className="size-4 text-white/50"/>;
    return <Goal className="size-4 text-flutlicht"/>;
}

/** A match report from DFBnet: result, events, and what else is in it */
function Spielberichtstafel({ereignisse = EREIGNISSE.length}: { ereignisse?: number }) {
    return (
        <Karte>
            <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-2.5">
                <span className="flex items-center gap-2 text-[13px]">
                    <ClipboardList className="size-4 text-white/55"/>
                    <span className="font-semibold">Spielbericht</span>
                    <span className="text-white/50">Sa 22.11. · Landesklasse</span>
                </span>
                <span className="text-[11px] text-white/45">Beispiel</span>
            </div>

            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 px-4 pt-3.5 pb-2 text-[12.5px]">
                <p className="text-right font-medium">FSV Lindenau</p>
                <p className="spesen-leuchtziffer font-mono text-[26px] leading-none font-semibold text-flutlicht">1 : 1</p>
                <p className="font-medium">SG Am Bergsee</p>
            </div>

            <ul className="divide-y divide-white/[0.07] px-4">
                {EREIGNISSE.slice(0, ereignisse).map((e) => (
                    <li key={e.minute} className={`flex items-center gap-3 py-1.5 ${e.gast ? 'flex-row-reverse text-right' : ''}`}>
                        <span className="w-8 shrink-0 font-mono text-[11px] text-white/50">{e.minute}</span>
                        <span className="grid w-4 shrink-0 place-items-center"><Symbol typ={e.typ}/></span>
                        <div className="min-w-0 flex-1 text-[12px]">
                            <p className="truncate font-medium">{e.person}</p>
                            <p className="text-[10.5px] text-white/50">{e.text}</p>
                        </div>
                    </li>
                ))}
            </ul>

            <div className="mt-1 grid grid-cols-3 gap-2 border-t border-white/10 p-3 text-[11px]">
                {[
                    {icon: Users, titel: 'Aufstellungen', text: '2 × 16 Spieler'},
                    {icon: Euro, titel: 'Kosten Gespann', text: '201,60 €'},
                    {icon: Paperclip, titel: 'Dokumente', text: 'Sonderbericht.pdf'},
                ].map((teil) => (
                    <div key={teil.titel} className="min-w-0 rounded-lg bg-white/[0.05] px-2.5 py-2">
                        <p className="flex items-center gap-1 font-medium">
                            <teil.icon className="size-3.5 shrink-0 text-flutlicht"/>
                            {teil.titel}
                        </p>
                        <p className="mt-0.5 truncate text-[10.5px] text-white/50">{teil.text}</p>
                    </div>
                ))}
            </div>
        </Karte>
    );
}

/* ---------- Slides ---------- */

/* 1 - Hook: a lot has happened since the last post */
function Ankuendigung() {
    return (
        <Folie anzahl={ANZAHL} nummer={1} feld>
            <Etikett>Update · Neu in Spesenfuchs</Etikett>
            <h1 className="mt-5 text-[52px] leading-[1.02] font-semibold tracking-[-0.035em]">
                Halbzeit.<br/>Zeit für <Leucht>Bilanz</Leucht>.
            </h1>
            <p className="mt-4 max-w-[28rem] text-[17px] leading-relaxed text-white/70">
                Seit dem letzten Beitrag ist viel passiert: Statistik, Fahrgemeinschaften, Spielberichte – und alles aus dem November-Update.
            </p>

            <div className={`relative ${STORY ? 'mt-8 h-[330px]' : 'mt-5 flex-1 [zoom:0.8]'}`}>
                <div className="absolute top-0 right-[-2rem] w-[86%]">
                    <Statistiktafel monate={false}/>
                </div>
                <div className={`absolute left-[-0.75rem] z-10 w-[84%] ${STORY ? 'top-[150px]' : 'top-[140px]'}`}>
                    <Karte className="px-4 py-3">
                        <p className="flex flex-wrap items-center gap-x-1.5 text-[13px] font-medium">
                            <Users className="size-4 shrink-0 text-flutlicht"/>
                            Fahrgemeinschaft
                            <span className="font-normal text-white/50">· 148 km</span>
                            <span className="text-[12px] font-normal text-flutlicht">spart 88 km</span>
                        </p>
                        <p className="mt-0.5 text-[12px] text-white/55">SR (du) fährt und holt SRA 1 und SRA 2 ab</p>
                    </Karte>
                </div>
            </div>
        </Folie>
    );
}

const SAISONS = ['26/27', '25/26', '24/25'];

const NOVEMBER = [
    {icon: ClipboardCheck, titel: 'Beobachtungen', text: 'Deine Noten je Saison als SR, Assistent und 4. Offizieller.'},
    {icon: Smartphone, titel: 'Als App', text: 'Auf den Homescreen legen – ohne Browserleiste, mit Tab-Leiste.'},
    {icon: Phone, titel: 'Fürs Handy gemacht', text: 'Gespann antippen, große Felder, klare Meldung im Funkloch.'},
];

/* 2 - Recap: the update story of November, for everyone who missed it */
function November() {
    return (
        <Folie anzahl={ANZAHL} nummer={2}>
            <Etikett>Schon im November</Etikett>
            <Titel>Noten, App und ein <Leucht>Heimspiel</Leucht> am Handy.</Titel>

            <div className={STORY ? 'mt-7' : 'mt-5 [zoom:0.85]'}>
                <Beobachtungstafel klassen={false} saisons={SAISONS}/>
            </div>

            <ul className={`grid gap-2.5 ${STORY ? 'mt-6' : 'mt-4'}`}>
                {NOVEMBER.map((punkt) => (
                    <li key={punkt.titel} className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.04] px-3.5 py-2.5">
                        <span className="grid size-9 shrink-0 place-items-center rounded-full border border-flutlicht/40 text-flutlicht">
                            <punkt.icon className="size-4"/>
                        </span>
                        <div className="min-w-0">
                            <p className="text-[14px] font-semibold">{punkt.titel}</p>
                            <p className="text-[12.5px] leading-snug text-white/60">{punkt.text}</p>
                        </div>
                    </li>
                ))}
            </ul>
        </Folie>
    );
}

/* 3 - The match list: Spiele tab, upcoming/past, search, months, refresh */
function Spiele() {
    return (
        <Folie anzahl={ANZAHL} nummer={3}>
            <Etikett>Neu: Spiele</Etikett>
            <Titel>Alle Spiele, <Leucht>eine Liste</Leucht>.</Titel>
            <p className="mt-4 text-[17px] leading-relaxed text-white/70">
                Kommend und vergangen getrennt, durchsuchbar, nach Monat sortiert – und oben steht, wann DFBnet zuletzt gelesen wurde.
            </p>

            <div className={STORY ? 'mt-7' : 'mt-5 [zoom:0.86]'}>
                <Spieleliste/>
            </div>

            <div className={`mx-auto w-[92%] [zoom:0.8] ${STORY ? 'mt-7' : 'mt-4'}`}>
                <Tableiste aktiv={1}/>
            </div>
        </Folie>
    );
}

/* 4 - Mileage suggestions with carpools and meeting points */
function Fahrten() {
    return (
        <Folie anzahl={ANZAHL} nummer={4}>
            <Etikett>Neu: Kilometer-Vorschläge</Etikett>
            <Titel>Wer fährt mit <Leucht>wem</Leucht>?</Titel>
            <p className="mt-4 text-[17px] leading-relaxed text-white/70">
                Spesenfuchs plant die Strecken des ganzen Gespanns und schlägt Fahrgemeinschaften vor – mit Abholen oder Treffpunkt.
            </p>

            <div className={STORY ? 'mt-7' : 'mt-5 [zoom:0.9]'}>
                <Fahrtvorschlaege/>
            </div>

            <ul className={`grid gap-1.5 text-[14px] text-white/75 ${STORY ? 'mt-6' : 'mt-4'}`}>
                <Haken>Echte Straßenkilometer vom Routenplaner</Haken>
                <Haken>Ein Tipp auf „Übernehmen“ füllt die Felder</Haken>
            </ul>
        </Folie>
    );
}

/* 5 - Statistics: expenses and travel costs per season, venue map */
function Statistik() {
    return (
        <Folie anzahl={ANZAHL} nummer={5}>
            <Etikett>Neu: Statistik</Etikett>
            <Titel>Was die Saison <Leucht>einbringt</Leucht>.</Titel>
            <p className="mt-4 text-[17px] leading-relaxed text-white/70">
                Spesen und Fahrtkosten je Monat. Fehlen Kilometer, schätzt Spesenfuchs sie – sichtbar markiert.
            </p>

            <div className={`grid gap-3 ${STORY ? 'mt-7' : 'mt-5 [zoom:0.86]'}`}>
                <Statistiktafel/>
                <Spielstaetten/>
            </div>
        </Folie>
    );
}

/* 6 - Match reports right at the match */
function Spielberichte() {
    return (
        <Folie anzahl={ANZAHL} nummer={6}>
            <Etikett>Neu: Spielberichte</Etikett>
            <Titel>Der Spielbericht <Leucht>gleich dabei</Leucht>.</Titel>
            <p className="mt-4 text-[17px] leading-relaxed text-white/70">
                Sobald DFBnet ihn freigibt, hängt er an deinem Spiel: Tore, Karten, Wechsel, Aufstellungen, Kosten und Dokumente.
            </p>

            <div className={STORY ? 'mt-7' : 'mt-5 [zoom:0.88]'}>
                <Spielberichtstafel ereignisse={STORY ? 5 : 4}/>
            </div>
        </Folie>
    );
}

/** The NOFV form: one sheet per referee */
function Nofv() {
    return (
        <div className="relative h-[100px] w-[110px]">
            {[2, 1, 0].map((stufe) => (
                <div
                    key={stufe}
                    className="absolute grid w-[84px] gap-1 rounded-md border border-white/15 bg-[oklch(0.26_0.03_158)] p-2 shadow-lg shadow-black/40"
                    style={{left: stufe * 12, top: stufe * 8}}
                >
                    <p className="text-[9px] font-semibold text-flutlicht">NOFV</p>
                    <span className="h-1.5 w-full rounded-full bg-white/20"/>
                    <span className="h-1.5 w-2/3 rounded-full bg-white/10"/>
                    <span className="h-1.5 w-3/4 rounded-full bg-white/10"/>
                    <p className="text-right text-[8px] text-white/45">{['SR', 'SRA 1', 'SRA 2'][stufe]}</p>
                </div>
            ))}
        </div>
    );
}

/** The match identifier on the expense receipt */
function Beleg() {
    return (
        <div className="w-[88%] rounded-lg bg-white/90 p-3 text-[10px] text-neutral-800 shadow-lg shadow-black/40">
            <p className="font-semibold">Spesenabrechnung</p>
            <div className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
                <span className="text-neutral-500">Spiel</span>
                <span>FSV Lindenau – SG Am Bergsee</span>
                <span className="text-neutral-500">Spielkennung</span>
                <span className="w-fit rounded bg-[oklch(0.9_0.12_150)] px-1 font-mono font-semibold">612003417</span>
            </div>
        </div>
    );
}

/** A whole season read straight from DFBnet */
function Saison() {
    return (
        <div className="grid w-[88%] gap-1.5">
            {['Aug', 'Sep', 'Okt', 'Nov', 'Dez'].map((monat, index) => (
                <div key={monat} className="grid grid-cols-[2rem_1fr] items-center gap-2 text-[10px] text-white/55">
                    <span>{monat}</span>
                    <span className="h-2 rounded-full bg-flutlicht/70" style={{width: `${[70, 85, 80, 75, 35][index]}%`, opacity: index === 4 ? 0.5 : 1}}/>
                </div>
            ))}
        </div>
    );
}

/** Login lock after wrong passwords */
function Sperre() {
    return (
        <div className="grid w-[88%] gap-2 text-[11px]">
            <div className="flex items-center gap-1.5">
                {[0, 1, 2, 3, 4].map((versuch) => (
                    <span key={versuch} className="size-3 rounded-full bg-red-400/70"/>
                ))}
                <Lock className="ml-1 size-4 text-flutlicht"/>
            </div>
            <p className="rounded-lg bg-white/[0.06] px-2.5 py-1.5 leading-snug text-white/70">Zu viele Versuche – Anmeldung für 15 Minuten gesperrt.</p>
        </div>
    );
}

/* 7 - The smaller things */
function Ausserdem() {
    return (
        <Folie anzahl={ANZAHL} nummer={7}>
            <Etikett>Außerdem</Etikett>
            <Titel>Mehr <Leucht>unter der Haube</Leucht>.</Titel>

            <div className="mt-6 grid grid-cols-2 gap-3">
                <Kachel icon={FileText} titel="NOFV-Abrechnung" text="Regionalliga und Oberliga: ein Blatt je Schiri.">
                    <Nofv/>
                </Kachel>
                <Kachel icon={Hash} titel="Spielkennung" text="Die DFBnet-Kennung steht jetzt auf jeder Abrechnung.">
                    <Beleg/>
                </Kachel>
                <Kachel icon={CalendarDays} titel="Ganze Saison" text="Ansetzungen kommen direkt aus DFBnet – für die ganze Saison.">
                    <Saison/>
                </Kachel>
                <Kachel icon={ShieldCheck} titel="Sicherer Login" text="Nach fünf falschen Passwörtern ist erst mal Pause.">
                    <Sperre/>
                </Kachel>
            </div>
        </Folie>
    );
}

/* 8 - Call to action */
function Aufruf() {
    return (
        <Folie anzahl={ANZAHL} nummer={8} feld>
            <Etikett>Schon live</Etikett>
            <Titel>Einfach <Leucht>neu laden</Leucht>.</Titel>
            <p className="mt-4 text-[17px] leading-relaxed text-white/70">
                Alles ist schon da. Spielberichte kommen mit dem nächsten Abruf in der Nacht dazu.
            </p>

            <Karte className={STORY ? 'mt-8' : 'mt-9'}>
                <div className="flex items-center gap-3 border-b border-white/10 px-4 py-2.5">
                    <span className="flex gap-1.5">
                        <span className="size-2.5 rounded-full bg-white/15"/>
                        <span className="size-2.5 rounded-full bg-white/15"/>
                        <span className="size-2.5 rounded-full bg-white/15"/>
                    </span>
                    <span className="flex flex-1 items-center gap-2 rounded-lg bg-black/30 px-3 py-1.5 text-[13px] text-white/70">
                        <Lock className="size-3.5 text-flutlicht"/>
                        {ADRESSE}
                    </span>
                </div>
                <div className="px-5 py-6 text-center">
                    <p className="spesen-leuchtziffer text-[29px] font-semibold tracking-tight text-flutlicht">{ADRESSE}</p>
                    <p className="mt-2 flex items-center justify-center gap-1.5 text-[14px] text-white/60">
                        {STORY ? <ArrowDown className="size-4"/> : <Link2 className="size-4"/>}
                        {STORY ? 'Noch nicht dabei? Unten auf den Link tippen' : 'Noch nicht dabei? Link in der Bio'}
                    </p>
                </div>
            </Karte>

            {/* Left free for the link sticker, which is only added in Instagram */}
            {STORY && <div className="h-[88px] shrink-0"/>}

            <ul className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[14px] text-white/70">
                {[
                    {text: 'Statistik', icon: ChartColumn},
                    {text: 'Fahrgemeinschaften', icon: Users},
                    {text: 'Spielberichte', icon: ClipboardList},
                ].map((eintrag) => (
                    <li key={eintrag.text} className="flex items-center gap-1.5">
                        <eintrag.icon className="size-4 text-flutlicht"/>
                        {eintrag.text}
                    </li>
                ))}
            </ul>

            <p className={`flex items-center justify-center gap-1.5 text-[13px] text-white/50 ${STORY ? 'mt-10' : 'mt-auto'}`}>
                <ShieldCheck className="size-4"/>
                Für Schiedsrichter des Thüringer Fußball-Verbandes
            </p>
        </Folie>
    );
}

export function Halbzeit() {
    return <Beitrag folien={[Ankuendigung, November, Spiele, Fahrten, Statistik, Spielberichte, Ausserdem, Aufruf]}/>;
}
