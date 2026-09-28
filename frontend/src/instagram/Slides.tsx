import type {ReactNode} from 'react';
import {ArrowDown, ArrowRight, Check, CheckCircle2, Lock, Route, ShieldCheck, Trophy, FileText, ChartColumn, Link2} from 'lucide-react';
import {Marke, Spielfeld} from '@/pages/Landing';
import {
    Abrechnungskarte,
    Anfahrtschip,
    Dokumente,
    Ligenauszug,
    Nachtuhr,
    Saisontafel,
    Spieleliste,
} from '@/components/landing/Schaufenster';

/*
 * Instagram-Beitrag zur Vorstellung von Spesenfuchs: fuenf Slides im Format
 * 3:4, gebaut aus denselben Bausteinen wie die Landingpage, mit deren
 * ausgedachten Beispieldaten. ?s=1 bis ?s=5 zeigt eine einzelne Slide fuer
 * den Export, ohne Parameter stehen alle untereinander.
 *
 * Mit ?f=story entstehen dieselben Slides als Story im Format 9:16. Oben und
 * unten bleibt dort Platz fuer die Leisten von Instagram (Fortschritt, Profil,
 * Antwortfeld); Wisch-Hinweis und Punkte entfallen, die Story hat ihre eigenen.
 * Auf der letzten Slide bleibt eine Luecke fuer den Link-Sticker.
 */

const ANZAHL = 5;
const ADRESSE = 'spesenfuchs.jan-vogt.dev';
const STORY = new URLSearchParams(window.location.search).get('f') === 'story';

function Fortschritt({nummer}: { nummer: number }) {
    return (
        <span className="flex items-center gap-1.5">
            {Array.from({length: ANZAHL}, (_, index) => (
                <span
                    key={index}
                    className={`h-1.5 rounded-full ${index + 1 === nummer ? 'w-6 bg-flutlicht' : 'w-1.5 bg-white/25'}`}
                />
            ))}
        </span>
    );
}

/** Rahmen jeder Slide: Nacht-Grund, Flutlicht, Korn, Marke oben, Fortschritt unten */
function Folie({nummer, feld, children}: { nummer: number; feld?: boolean; children: ReactNode }) {
    return (
        <section className={`ig-slide spesen-nacht spesen-landing relative isolate flex w-[540px] flex-col overflow-hidden text-white ${STORY ? 'h-[960px]' : 'h-[720px]'}`}>
            {feld && (
                <div className="spesen-feld pointer-events-none absolute inset-x-0 bottom-0 h-[55%]">
                    <div className="absolute inset-0">
                        <div className="spesen-rasen absolute inset-0"/>
                        <Spielfeld className="absolute inset-x-[6%] inset-y-[8%] h-[84%] w-[88%] text-white/20"/>
                    </div>
                </div>
            )}
            <div className="spesen-strahl spesen-flutlicht pointer-events-none absolute inset-0"/>
            <div className="spesen-koerner pointer-events-none absolute inset-0"/>

            <header className={`relative flex items-center justify-between px-10 ${STORY ? 'pt-[118px]' : 'pt-9'}`}>
                <span className="[zoom:1.15]"><Marke hell/></span>
                <span className="text-[13px] font-medium text-white/45 tabular-nums">{nummer} / {ANZAHL}</span>
            </header>

            <div className={`relative flex min-h-0 flex-1 flex-col px-10 pt-7 ${STORY ? 'justify-center pb-[130px]' : ''}`}>
                {children}
            </div>

            {!STORY && <footer className="relative flex items-center justify-between px-10 pt-5 pb-9">
                <Fortschritt nummer={nummer}/>
                {nummer < ANZAHL ? (
                    <span className="flex items-center gap-1.5 text-[13px] font-medium text-white/55">
                        Wischen
                        <ArrowRight className="size-4"/>
                    </span>
                ) : (
                    <span className="flex items-center gap-1.5 text-[13px] font-medium text-flutlicht">
                        <Link2 className="size-4"/>
                        Link in Bio
                    </span>
                )}
            </footer>}
        </section>
    );
}

function Etikett({children}: { children: ReactNode }) {
    return (
        <p className="inline-flex w-fit items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[13px] font-medium text-white/80">
            <span className="size-1.5 rounded-full bg-flutlicht"/>
            {children}
        </p>
    );
}

function Titel({children}: { children: ReactNode }) {
    return (
        <h2 className="mt-4 text-[40px] leading-[1.05] font-semibold tracking-[-0.03em] text-balance">{children}</h2>
    );
}

function Leucht({children}: { children: ReactNode }) {
    return <span className="spesen-leuchtschrift text-flutlicht">{children}</span>;
}

/* 1 - Aufhaenger: das Versprechen und die Anwendung dazu */
function Ankuendigung() {
    return (
        <Folie nummer={1} feld>
            <Etikett>Neu für Schiedsrichter im TFV</Etikett>
            <h1 className="mt-5 text-[52px] leading-[1.02] font-semibold tracking-[-0.035em]">
                Abpfiff für den<br/><Leucht>Papierkram</Leucht>.
            </h1>
            <p className="mt-4 max-w-[27rem] text-[17px] leading-relaxed text-white/70">
                Deine Spesenabrechnungen entstehen jede Nacht aus deinen DFBnet-Ansetzungen – automatisch.
            </p>

            {/* Die Abrechnung liegt unter der ersten Ansetzung - sie ist deren Beleg */}
            <div className={`relative flex-1 ${STORY ? 'mt-8 [zoom:0.88]' : 'mt-5 [zoom:0.75]'}`}>
                <div className="absolute top-0 right-[-2rem] w-[86%]">
                    <Spieleliste/>
                </div>
                <div className="absolute top-[94px] left-[-0.75rem] z-10 w-[80%]">
                    <Abrechnungskarte/>
                </div>
            </div>
        </Folie>
    );
}

const AUFGABEN: { text: string; selbst?: boolean }[] = [
    {text: 'Ansetzung aus DFBnet abtippen'},
    {text: 'Satz in der Spesenordnung suchen'},
    {text: 'Gespann und Anschriften sammeln'},
    {text: 'Pokal: Klasse der Vereine prüfen'},
    {text: 'Formular ausfüllen, als PDF sichern'},
    {text: 'Kilometer eintragen', selbst: true},
];

/* 2 - Das Problem: was nach jedem Spiel ansteht und was davon wegfaellt */
function Problem() {
    return (
        <Folie nummer={2}>
            <Etikett>Kennst du das?</Etikett>
            <Titel>Nach dem Spiel ist <Leucht>vor der Abrechnung</Leucht>.</Titel>
            <p className="mt-4 text-[17px] leading-relaxed text-white/70">
                Nach jedem Spiel dieselbe Liste. Spesenfuchs streicht fast alles davon.
            </p>

            <ul className="mt-6 overflow-hidden rounded-2xl border border-white/15 bg-[oklch(0.215_0.03_158)] shadow-2xl shadow-black/50">
                {AUFGABEN.map((aufgabe) => (
                    <li
                        key={aufgabe.text}
                        className={`flex items-center justify-between gap-3 border-b border-white/[0.07] px-4 last:border-b-0 ${STORY ? 'py-4' : 'py-3'}`}
                    >
                        {aufgabe.selbst ? (
                            <span className="text-[15px] font-medium text-white">{aufgabe.text}</span>
                        ) : (
                            <span className="text-[15px] text-white/45 line-through decoration-flutlicht/70 decoration-2">
                                {aufgabe.text}
                            </span>
                        )}
                        {aufgabe.selbst ? (
                            <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-dashed border-white/30 px-2.5 py-1 text-xs text-white/75">
                                <Route className="size-3.5"/>
                                du, mit Karte
                            </span>
                        ) : (
                            <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-flutlicht/15 px-2.5 py-1 text-xs font-medium text-flutlicht">
                                <Check className="size-3.5"/>
                                automatisch
                            </span>
                        )}
                    </li>
                ))}
            </ul>
        </Folie>
    );
}

const SCHRITTE = [
    {phase: 'Aufwärmen', titel: 'Registrieren', chip: 'einmalig', text: 'Account anlegen, DFBnet-Zugang hinterlegen.'},
    {phase: 'Anpfiff', titel: 'Ansetzungen abrufen', chip: 'jede Nacht · 03:00', text: 'Deine Spiele kommen jede Nacht aus DFBnet.'},
    {phase: 'Halbzeit', titel: 'Kilometer eintragen', chip: 'je Spiel', text: 'Satz, Gespann und Spielstätte stehen drin.'},
    {phase: 'Abpfiff', titel: 'Herunterladen', chip: 'Word · PDF', text: 'Laden, unterschreiben, einreichen. Fertig.'},
];

/* 3 - So geht's: der Spielablauf in vier Schritten */
function Ablauf() {
    return (
        <Folie nummer={3}>
            <div className="flex items-start justify-between gap-4">
                <div>
                    <Etikett>So geht's</Etikett>
                    <Titel>Vier Schritte bis <Leucht>zum Abpfiff</Leucht>.</Titel>
                </div>
                <Nachtuhr className="mt-1 size-20 shrink-0"/>
            </div>

            <ol className={`relative mt-6 grid ${STORY ? 'gap-5' : 'gap-3'}`}>
                <span className="absolute top-5 bottom-8 left-[19px] w-px bg-gradient-to-b from-flutlicht/70 via-flutlicht/30 to-flutlicht/10"/>
                {SCHRITTE.map((schritt, index) => (
                    <li key={schritt.titel} className="relative grid grid-cols-[40px_1fr] gap-4">
                        <span
                            className={`grid size-10 place-items-center rounded-full text-[15px] font-semibold tabular-nums ${
                                index === 0 ? 'spesen-ball bg-flutlicht text-nacht' : 'border border-flutlicht/40 bg-nacht text-flutlicht'
                            }`}
                        >
                            {index + 1}
                        </span>
                        <div className={`rounded-xl border border-white/10 bg-white/[0.04] px-4 ${STORY ? 'py-3.5' : 'py-2.5'}`}>
                            <div className="flex items-center justify-between gap-2">
                                <span className="text-[11px] font-medium tracking-wider text-white/45 uppercase">{schritt.phase}</span>
                                <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-white/75">{schritt.chip}</span>
                            </div>
                            <p className="text-[17px] font-semibold">{schritt.titel}</p>
                            <p className="mt-0.5 text-[14px] leading-snug text-white/65">{schritt.text}</p>
                        </div>
                    </li>
                ))}
            </ol>
        </Folie>
    );
}

function Kachel({icon: Icon, titel, text, children}: {
    icon: typeof Route;
    titel: string;
    text: string;
    children: ReactNode;
}) {
    return (
        <div className="flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04]">
            <div className={`flex items-center justify-center bg-black/20 p-3 ${STORY ? 'h-[156px]' : 'h-[132px]'}`}>{children}</div>
            <div className="border-t border-white/10 px-3.5 py-2.5">
                <p className="flex items-center gap-1.5 text-[14px] font-semibold">
                    <Icon className="size-4 text-flutlicht"/>
                    {titel}
                </p>
                <p className="mt-1 text-[12.5px] leading-snug text-white/60">{text}</p>
            </div>
        </div>
    );
}

/* 4 - Was drinsteckt: vier Belege aus der Anwendung */
function Funktionen() {
    return (
        <Folie nummer={4}>
            <Etikett>Was drinsteckt</Etikett>
            <Titel>Mehr als nur <Leucht>Spesen</Leucht>.</Titel>

            <div className="mt-6 grid grid-cols-2 gap-3">
                <Kachel icon={Route} titel="Fahrt mit Karte" text="Gespann und Spielstätte auf einer Karte, 0,30 € je km.">
                    <div className="w-[80%]"><Anfahrtschip/></div>
                </Kachel>
                <Kachel icon={Trophy} titel="Pokal eingestuft" text="Es zählt die Klasse der Vereine – aus den Tabellen.">
                    <div className="w-full [zoom:0.84]"><Ligenauszug/></div>
                </Kachel>
                <Kachel icon={ChartColumn} titel="Deine Saison" text="Einsätze, Karten, Lehrabende und Gespanne.">
                    <div className={`w-full ${STORY ? '[zoom:0.72]' : '[zoom:0.64]'}`}><Saisontafel/></div>
                </Kachel>
                <Kachel icon={FileText} titel="Word & PDF" text="Einzeln laden oder alle zusammen als ZIP.">
                    <div className="[zoom:0.9]"><Dokumente/></div>
                </Kachel>
            </div>

        </Folie>
    );
}

/* 5 - Aufruf: die Adresse, gross genug zum Abtippen */
function Aufruf() {
    return (
        <Folie nummer={5} feld>
            <Etikett>Jetzt live</Etikett>
            <Titel>Bereit für den <Leucht>Anpfiff</Leucht>?</Titel>
            <p className="mt-4 text-[17px] leading-relaxed text-white/70">
                Registrieren, DFBnet verbinden – die nächste Abrechnung schreibt sich von selbst.
            </p>

            <div className={`overflow-hidden rounded-2xl ${STORY ? 'mt-8' : 'mt-9'} border border-white/15 bg-[oklch(0.215_0.03_158)] shadow-2xl shadow-black/60`}>
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
                        {STORY ? 'oder direkt unten auf den Link tippen' : 'oder direkt über den Link in der Bio'}
                    </p>
                </div>
            </div>

            {/* Frei fuer den Link-Sticker, der erst in Instagram dazukommt */}
            {STORY && <div className="h-[88px] shrink-0"/>}

            <ul className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[14px] text-white/70">
                {['Ohne Installation', 'Verschlüsselt', 'Für Handy & PC'].map((eintrag) => (
                    <li key={eintrag} className="flex items-center gap-1.5">
                        <CheckCircle2 className="size-4 text-flutlicht"/>
                        {eintrag}
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

const FOLIEN = [Ankuendigung, Problem, Ablauf, Funktionen, Aufruf];

export function Slides() {
    const gewaehlt = Number(new URLSearchParams(window.location.search).get('s'));
    const folien = gewaehlt >= 1 && gewaehlt <= ANZAHL ? [FOLIEN[gewaehlt - 1]] : FOLIEN;

    return (
        <div className={gewaehlt ? '' : 'grid justify-center gap-6 bg-neutral-900 p-6'}>
            {folien.map((Inhalt, index) => <Inhalt key={index}/>)}
        </div>
    );
}
