import type {ReactNode} from 'react';
import {
    AlertCircle,
    ArrowDown,
    CheckCircle2,
    ClipboardCheck,
    Download,
    Ellipsis,
    FileText,
    LayoutDashboard,
    LayoutGrid,
    Link2,
    Lock,
    Mail,
    Phone,
    Route,
    Share,
    ShieldCheck,
    Smartphone,
    SquarePlus,
    Table2,
    Trophy,
    WifiOff,
} from 'lucide-react';
import {ADRESSE, Beitrag, Etikett, Folie, Kachel, Leucht, STORY, Titel} from './Rahmen';

/*
 * Instagram story for the update: what has been added since the introduction
 * in September. Five slides in the same frame as the first post
 * (Slides.tsx), reachable at /instagram-update.html with ?s=1 to ?s=5;
 * meant for &f=story (9:16), without the parameter the same is produced in 3:4.
 *
 * The excerpts are recreated, the data made up - like on the
 * landing page. The grades follow the scales of the referee observation: around 240 points as referee, around 60 as assistant.
 */

const ANZAHL = 5;

/** Opaque card like the statement on the landing page */
function Karte({className = '', children}: { className?: string; children: ReactNode }) {
    return (
        <div className={`overflow-hidden rounded-2xl border border-white/15 bg-[oklch(0.215_0.03_158)] text-white shadow-2xl shadow-black/60 ${className}`}>
            {children}
        </div>
    );
}

const SCHNITTE = [
    {label: 'Schiedsrichter', schnitt: '243,50', anzahl: '4 Beobachtungen'},
    {label: 'Assistent', schnitt: '61,50', anzahl: '2 Beobachtungen'},
];

const KLASSEN = [
    {klasse: 'Thüringenliga', sr: '242,00', srAnzahl: 2, sra: '61,50', sraAnzahl: 2},
    {klasse: 'Landesklasse', sr: '245,00', srAnzahl: 2, sra: null, sraAnzahl: 0},
];

/** The new tab "Beobachtungen": average per role, for the men's leagues per league class */
function Beobachtungstafel({klassen = true}: { klassen?: boolean }) {
    return (
        <Karte>
            <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-2.5">
                <span className="flex items-center gap-2 text-[13px]">
                    <ClipboardCheck className="size-4 text-white/55"/>
                    <span className="font-semibold">Herren</span>
                    <span className="text-white/50">Schiri-Beobachtung</span>
                </span>
                <span className="text-[11px] text-white/45">Beispiel</span>
            </div>

            <div className="grid gap-3 p-4">
                <div className="flex gap-1.5">
                    {['25/26', '24/25', '23/24'].map((saison, index) => (
                        <span
                            key={saison}
                            className={`rounded-md px-2.5 py-1 text-[12px] font-medium ${index === 0 ? 'bg-flutlicht/15 text-flutlicht' : 'text-white/45'}`}
                        >
                            {saison}
                        </span>
                    ))}
                </div>

                <div className="grid grid-cols-2 gap-2.5">
                    {SCHNITTE.map((x) => (
                        <div key={x.label} className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5">
                            <p className="text-[11.5px] text-white/55">{x.label}</p>
                            <p className="mt-0.5 font-mono text-[26px] leading-tight font-semibold tracking-tight">
                                <span className="mr-1 text-[15px] font-normal text-white/45">Ø</span>
                                {x.schnitt}
                            </p>
                            <p className="text-[11px] text-white/45">{x.anzahl}</p>
                        </div>
                    ))}
                </div>

                {klassen && (
                    <div className="overflow-hidden rounded-xl border border-white/10 text-[12px]">
                        <div className="grid grid-cols-[1fr_5.5rem_5.5rem] gap-2 border-b border-white/10 px-3 py-1.5 text-[10.5px] tracking-wider text-white/45 uppercase">
                            <span>Spielklasse</span>
                            <span className="text-right">SR</span>
                            <span className="text-right">Assistent</span>
                        </div>
                        {KLASSEN.map((zeile) => (
                            <div key={zeile.klasse} className="grid grid-cols-[1fr_5.5rem_5.5rem] gap-2 border-b border-white/[0.07] px-3 py-1.5 last:border-b-0">
                                <span>{zeile.klasse}</span>
                                <span className="text-right">
                                    <span className="font-mono">{zeile.sr}</span>
                                    <span className="ml-1 text-[10.5px] text-white/45">({zeile.srAnzahl})</span>
                                </span>
                                <span className="text-right">
                                    {zeile.sra ? (
                                        <>
                                            <span className="font-mono">{zeile.sra}</span>
                                            <span className="ml-1 text-[10.5px] text-white/45">({zeile.sraAnzahl})</span>
                                        </>
                                    ) : (
                                        <span className="text-white/35">–</span>
                                    )}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </Karte>
    );
}

const TABS = [
    {label: 'Dashboard', icon: LayoutDashboard},
    {label: 'Spesen', icon: FileText},
    {label: 'Saison', icon: Trophy},
    {label: 'Ligen', icon: Table2},
    {label: 'Mehr', icon: Ellipsis},
];

/** The floating tab bar of the phone */
function Tableiste({aktiv = 0}: { aktiv?: number }) {
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

/** Key figure from the dashboard, as it now sits side by side on the phone */
function Kennzahl({label, wert, zusatz}: { label: string; wert: string; zusatz: string }) {
    return (
        <div className="min-w-0 rounded-xl border border-white/10 bg-white/[0.04] px-2.5 py-2">
            <p className="truncate text-[9.5px] text-white/50">{label}</p>
            <p className="truncate text-[17px] leading-tight font-semibold tabular-nums">{wert}</p>
            <p className="truncate text-[9px] text-white/40">{zusatz}</p>
        </div>
    );
}

/** A phone with Spesenfuchs installed: no browser, the tab bar at the bottom */
function Handy() {
    return (
        <div className="relative h-full w-full overflow-hidden rounded-[2.1rem] border-[5px] border-[oklch(0.3_0.02_158)] bg-nacht shadow-2xl shadow-black/70">
            <div className="flex items-center justify-between px-5 pt-2.5 text-[10px] font-semibold text-white/80">
                <span className="tabular-nums">9:41</span>
                <span className="h-4 w-14 rounded-full bg-black"/>
                <span className="flex gap-0.5">
                    <span className="h-2 w-1 rounded-sm bg-white/70"/>
                    <span className="h-2 w-1 rounded-sm bg-white/70"/>
                    <span className="h-2 w-1 rounded-sm bg-white/40"/>
                </span>
            </div>

            <div className="grid gap-2 px-3 pt-4 [zoom:0.8]">
                <p className="text-[17px] font-semibold">Dashboard</p>
                <div className="grid grid-cols-2 gap-2">
                    <Kennzahl label="Spiele in 25/26" wert="29" zusatz="18 als SR"/>
                    <Kennzahl label="Kartenschnitt" wert="1,6" zusatz="je Spiel"/>
                    <Kennzahl label="Nächstes Spiel" wert="Sa 14:00" zusatz="Landesklasse"/>
                    <Kennzahl label="Ohne Kilometer" wert="1" zusatz="Abrechnung"/>
                </div>
                {[0, 1].map((karte) => (
                    <div key={karte} className="mt-1 grid gap-1.5 rounded-xl border border-white/10 bg-white/[0.04] p-2.5">
                        <span className="h-2 w-3/4 rounded-full bg-white/20"/>
                        <span className="h-2 w-1/2 rounded-full bg-white/10"/>
                        <span className="h-2 w-2/3 rounded-full bg-white/10"/>
                    </div>
                ))}
            </div>

            <div className="absolute inset-x-2 bottom-3 [zoom:0.66]">
                <Tableiste/>
            </div>
        </div>
    );
}

/* 1 - Hook: there is something new, with a view of the biggest part of it */
function Ankuendigung() {
    return (
        <Folie anzahl={ANZAHL} nummer={1} feld>
            <Etikett>Update · Neu in Spesenfuchs</Etikett>
            <h1 className="mt-5 text-[52px] leading-[1.02] font-semibold tracking-[-0.035em]">
                Nachspielzeit<br/>mit <Leucht>Neuem</Leucht>.
            </h1>
            <p className="mt-4 max-w-[27rem] text-[17px] leading-relaxed text-white/70">
                Seit dem Anpfiff im September ist einiges dazugekommen: deine Beobachtungen, die App fürs Handy und viel Feinschliff.
            </p>

            <div className={`relative ${STORY ? 'mt-8 h-[330px]' : 'mt-5 flex-1 [zoom:0.8]'}`}>
                <div className="absolute top-0 right-[-2rem] w-[80%]">
                    <Beobachtungstafel klassen={false}/>
                </div>
                <div className={`absolute left-[-0.75rem] z-10 w-[78%] ${STORY ? 'top-[218px]' : 'top-[200px]'}`}>
                    <Tableiste aktiv={4}/>
                </div>
            </div>
        </Folie>
    );
}

const HINWEISE = [
    'Ein Schnitt je Saison als SR, Assistent und 4. Offizieller',
    'Bei den Herren zusätzlich je Spielklasse',
    'Jede Note einzeln, mit Spiel und Beobachter',
];

/* 2 - Observations: the new tab */
function Beobachtungen() {
    return (
        <Folie anzahl={ANZAHL} nummer={2}>
            <Etikett>Neu: Beobachtungen</Etikett>
            <Titel>Deine Noten auf <Leucht>einen Blick</Leucht>.</Titel>
            <p className="mt-4 text-[17px] leading-relaxed text-white/70">
                Spesenfuchs liest deine Beobachtungen aus DFBnet mit – aus der Schiri-Beobachtung und, wer es hat, dem Schiri-Portal.
            </p>

            <div className={STORY ? 'mt-7' : 'mt-5 [zoom:0.9]'}>
                <Beobachtungstafel/>
            </div>

            <ul className={`grid gap-1.5 text-[14px] text-white/75 ${STORY ? 'mt-6' : 'mt-4'}`}>
                {HINWEISE.map((hinweis) => (
                    <li key={hinweis} className="flex items-center gap-2">
                        <CheckCircle2 className="size-4 shrink-0 text-flutlicht"/>
                        {hinweis}
                    </li>
                ))}
            </ul>
        </Folie>
    );
}

const INSTALLATION = [
    {geraet: 'iPhone', icon: Share, text: 'In Safari auf „Teilen“, dann „Zum Home-Bildschirm“.'},
    {geraet: 'Android & PC', icon: Download, text: 'Im Dashboard auf „App installieren“ tippen.'},
    {geraet: 'Danach', icon: SquarePlus, text: 'Eigenes Symbol, keine Browserleiste.'},
];

/* 3 - As an app: installable, with tab bar */
function App() {
    return (
        <Folie anzahl={ANZAHL} nummer={3}>
            <Etikett>Neu: als App</Etikett>
            <Titel>Ab auf den <Leucht>Homescreen</Leucht>.</Titel>
            <p className="mt-4 text-[17px] leading-relaxed text-white/70">
                Spesenfuchs lässt sich jetzt installieren – unten die Tab-Leiste, wie in jeder App.
            </p>

            <div className={`grid grid-cols-[190px_1fr] gap-5 ${STORY ? 'mt-8 h-[390px]' : 'mt-6 min-h-0 flex-1'}`}>
                <Handy/>

                <ol className="relative grid content-center gap-3">
                    <span className="absolute top-6 bottom-6 left-[17px] w-px bg-gradient-to-b from-flutlicht/70 via-flutlicht/30 to-flutlicht/10"/>
                    {INSTALLATION.map((schritt, index) => (
                        <li key={schritt.geraet} className="relative grid grid-cols-[36px_1fr] gap-3">
                            <span
                                className={`grid size-9 place-items-center rounded-full ${
                                    index === 0 ? 'spesen-ball bg-flutlicht text-nacht' : 'border border-flutlicht/40 bg-nacht text-flutlicht'
                                }`}
                            >
                                <schritt.icon className="size-4"/>
                            </span>
                            <div className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2">
                                <p className="text-[14px] font-semibold">{schritt.geraet}</p>
                                <p className="mt-0.5 text-[12.5px] leading-snug text-white/65">{schritt.text}</p>
                            </div>
                        </li>
                    ))}
                </ol>
            </div>
        </Folie>
    );
}

/** A colleague on the crew, phone and e-mail tappable */
function Kontakt() {
    return (
        <div className="w-full rounded-xl border border-white/10 bg-black/25 p-3 text-[11.5px]">
            <p className="flex items-center justify-between">
                <span className="font-medium">SRA 1</span>
                <span className="text-white/45">Gespann</span>
            </p>
            <p className="mt-2 flex items-center gap-2 text-flutlicht">
                <Phone className="size-3.5"/>
                <span className="underline underline-offset-2">0361 123456</span>
            </p>
            <p className="mt-1.5 flex items-center gap-2 text-flutlicht">
                <Mail className="size-3.5"/>
                <span className="underline underline-offset-2">sra@beispiel.de</span>
            </p>
        </div>
    );
}

/** The kilometer field in thumb size */
function Kilometerfeld() {
    return (
        <div className="w-[85%] text-[11.5px]">
            <p className="mb-1.5 text-white/55">Kilometer SR</p>
            <div className="flex h-12 items-center justify-between rounded-xl border-2 border-flutlicht/70 bg-black/30 px-3 shadow-[0_0_0_4px] shadow-flutlicht/15">
                <span className="text-[19px] font-semibold tabular-nums">42<span className="ml-0.5 inline-block h-5 w-px translate-y-0.5 bg-flutlicht"/></span>
                <span className="text-white/45">km</span>
            </div>
        </div>
    );
}

/** The key figures of the dashboard, now side by side on the phone */
function Kennzahlen() {
    return (
        <div className="grid w-full grid-cols-2 gap-2">
            <Kennzahl label="Spiele in 25/26" wert="29" zusatz="18 als SR"/>
            <Kennzahl label="Kartenschnitt" wert="1,6" zusatz="je Spiel"/>
            <Kennzahl label="Nächstes Spiel" wert="Sa 14:00" zusatz="Landesklasse"/>
            <Kennzahl label="Ohne Kilometer" wert="1" zusatz="Abrechnung"/>
        </div>
    );
}

/** Dead zone: a clear message instead of "Network Error" */
function Funkloch() {
    return (
        <div className="grid w-full gap-2 text-[11.5px]">
            <p className="w-fit rounded-md bg-white/5 px-2 py-0.5 font-mono text-white/35 line-through decoration-white/40">Network Error</p>
            <div className="flex items-start gap-2 rounded-lg bg-red-500/10 px-3 py-2 ring-1 ring-red-400/25">
                <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-red-300"/>
                <p className="leading-snug text-red-200">Keine Verbindung zum Server. Prüfe deine Internetverbindung.</p>
            </div>
        </div>
    );
}

/* 4 - Polish: what has gotten better on the phone */
function Feinschliff() {
    return (
        <Folie anzahl={ANZAHL} nummer={4}>
            <Etikett>Feinschliff</Etikett>
            <Titel>Am Handy jetzt ein <Leucht>Heimspiel</Leucht>.</Titel>

            <div className="mt-6 grid grid-cols-2 gap-3">
                <Kachel icon={Phone} titel="Gespann anrufen" text="Telefon und E-Mail der Kollegen einfach antippen.">
                    <Kontakt/>
                </Kachel>
                <Kachel icon={Route} titel="Daumengroße Felder" text="Kilometer bequem tippen, Safari zoomt nicht mehr rein.">
                    <Kilometerfeld/>
                </Kachel>
                <Kachel icon={LayoutGrid} titel="Alles im Blick" text="Die Zahlen im Dashboard stehen nebeneinander.">
                    <Kennzahlen/>
                </Kachel>
                <Kachel icon={WifiOff} titel="Klar im Funkloch" text="Ohne Netz sagt die App, was los ist.">
                    <Funkloch/>
                </Kachel>
            </div>
        </Folie>
    );
}

/* 5 - Call to action: the update is already here */
function Aufruf() {
    return (
        <Folie anzahl={ANZAHL} nummer={5} feld>
            <Etikett>Schon live</Etikett>
            <Titel>Einfach <Leucht>neu laden</Leucht>.</Titel>
            <p className="mt-4 text-[17px] leading-relaxed text-white/70">
                Das Update ist schon da. Deine Beobachtungen kommen mit dem nächsten Abruf in der Nacht dazu.
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
                    {text: 'Beobachtungen', icon: ClipboardCheck},
                    {text: 'Als App', icon: Smartphone},
                    {text: 'Fürs Handy gemacht', icon: CheckCircle2},
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

export function Update() {
    return <Beitrag folien={[Ankuendigung, Beobachtungen, App, Feinschliff, Aufruf]}/>;
}
