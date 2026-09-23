import {type CSSProperties, type ReactNode, type RefObject, useEffect, useLayoutEffect, useRef, useState} from 'react';
import {Link} from 'react-router-dom';
import {Button} from '@/components/ui/button';
import {api} from '@/lib/api';
import {isAuthenticated} from '@/lib/auth';
import {magKeineBewegung, useCountUp, useImBild, useRevealOnScroll, useScrollProgress} from '@/hooks/useReveal';
import {
    Abrechnungskarte,
    Anfahrtschip,
    Anfahrtskarte,
    Dokumente,
    Ligenauszug,
    Nachtuhr,
    Saisontafel,
    Spieleliste,
    Stammdatenauszug,
} from '@/components/landing/Schaufenster';
import {
    ArrowRight,
    ChartColumn,
    CheckCircle2,
    Clock,
    Eye,
    FileText,
    IdCard,
    Lock,
    Mail,
    MoonStar,
    Pause,
    Play,
    Plus,
    Route,
    Scale,
    Trash2,
    Trophy,
    type LucideIcon,
} from 'lucide-react';

/**
 * Spesensaetze der TFV-Spesenordnung §2 Abs. 2a (Maenner, Punktspiele) und
 * ein paar Zeilen daneben. Sie stehen hier nur als Schaufenster - gerechnet
 * wird ausschliesslich im Backend, siehe generator/spesen_calculator.py.
 */
const SPESENSAETZE = [
    {klasse: 'Verbandsliga', sr: '50,00 €', sra: '40,00 €'},
    {klasse: 'Landesklasse', sr: '40,00 €', sra: '30,00 €'},
    {klasse: 'Kreisoberliga', sr: '30,00 €', sra: '25,00 €'},
    {klasse: 'Kreisliga', sr: '25,00 €', sra: '23,00 €'},
    {klasse: 'Kreisklasse', sr: '25,00 €', sra: '23,00 €'},
    {klasse: 'Frauen, Verbandsliga', sr: '25,00 €', sra: '20,00 €'},
    {klasse: 'A-/B-Junioren, Landesebene', sr: '25,00 €', sra: '20,00 €'},
    {klasse: 'Alte Herren, Kreisebene', sr: '25,00 €', sra: '23,00 €'},
];

/*
 * Quelle der Saetze; der Stand bricht nur als Ganzes um. Das umschliessende
 * span haelt den Text zusammen, wenn er in einem Flex-Element steht - dort
 * fiele sonst das Leerzeichen vor "Stand" weg.
 */
const QUELLE = (
    <span>
        TFV-Spesenordnung §2 · SR / SRA · <span className="whitespace-nowrap">Stand 01.07.2025</span>
    </span>
);

/**
 * Innenrahmen aller Abschnitte, damit die Kanten untereinander fluchten. Den
 * seitlichen Rand setzt .spesen-rahmen (1rem, ab sm 1.5rem, ab lg 2.5rem),
 * am iPhone quer mindestens so breit wie die sicheren Raender.
 */
const RAHMEN = 'spesen-rahmen mx-auto w-full max-w-[90rem]';

interface Funktion {
    icon: LucideIcon;
    title: string;
    description: string;
    /** Der kleine Beleg ueber dem Text - ein Ausschnitt aus der Anwendung */
    bild: ReactNode;
}

/** Die hellen Kacheln der Aufstellung. Die zwei dunklen stehen darunter einzeln. */
const FUNKTIONEN: Funktion[] = [
    {
        icon: Route,
        title: 'Fahrtkosten mit Karte',
        description: 'Kilometer eintragen, den Rest rechnet Spesenfuchs mit 0,30 € je km. ' +
            'Die Karte zeigt die Anschriften des Gespanns und die Spielstätte.',
        bild: <Anfahrtskarte className="h-full w-auto max-w-full"/>,
    },
    {
        icon: Trophy,
        title: 'Pokal richtig eingestuft',
        description: 'Bei Pokal- und Freundschaftsspielen zählt die Klasse der Vereine – nachgeschlagen ' +
            'in den Tabellen von Thüringenliga und Landesklasse. Unsicher? Dann bleibt das Feld leer.',
        bild: <Ligenauszug/>,
    },
    {
        icon: FileText,
        title: 'Word & PDF',
        description: 'Jede Abrechnung als bearbeitbares DOCX und fertiges PDF, einzeln oder alle zusammen als ZIP.',
        bild: <Dokumente/>,
    },
    {
        icon: IdCard,
        title: 'Stammdaten & QMax',
        description: 'Deine DFBnet-Stammdaten samt Qualifikations-Maximum auf einen Blick, ' +
            'die persönlichen Angaben verschlüsselt gespeichert.',
        bild: <Stammdatenauszug/>,
    },
];

const SCHRITTE = [
    {
        phase: 'Aufwärmen',
        title: 'Registrieren',
        chip: 'einmalig',
        description: 'Account anlegen und deine DFBnet-Zugangsdaten ein einziges Mal hinterlegen.',
    },
    {
        phase: 'Anpfiff',
        title: 'Ansetzungen abrufen',
        chip: 'jede Nacht · 03:00',
        description: 'Spesenfuchs holt deine Ansetzungen aus DFBnet – nachts von allein oder sofort auf Knopfdruck.',
    },
    {
        phase: 'Halbzeit',
        title: 'Kilometer eintragen',
        chip: 'je Spiel',
        description: 'Satz, Gespann und Spielstätte stehen schon drin. Du trägst die Kilometer ein, die Karte hilft.',
    },
    {
        phase: 'Abpfiff',
        title: 'Herunterladen & einreichen',
        chip: 'Word · PDF · ZIP',
        description: 'Abrechnung als Word oder PDF laden, unterschreiben, einreichen. Fertig.',
    },
];

const FAIRPLAY = [
    {
        icon: Eye,
        title: 'Nur lesend',
        description: 'Spesenfuchs liest deine Daten aus DFBnet und schreibt nichts dorthin zurück.',
    },
    {
        icon: Lock,
        title: 'Verschlüsselt',
        description: 'Zugangsdaten und persönliche Stammdaten liegen verschlüsselt, Passwörter nur als Hash. Keine Weitergabe an Dritte.',
    },
    {
        icon: Scale,
        title: 'Lieber leer als falsch',
        description: 'Lässt sich ein Satz nicht sicher bestimmen, bleibt das Feld frei – statt eines Betrags, der nur plausibel aussieht.',
    },
    {
        icon: Trash2,
        title: 'Löschen per Mail',
        description: 'Eine kurze Mail genügt, dann werden dein Konto und alle zugehörigen Daten gelöscht.',
    },
];

/** Verweise in einer Antwort: im Fliesstext unterstrichen, damit sie auch ohne Farbe auffallen */
const ANTWORT_LINK = 'font-medium text-primary underline underline-offset-2 hover:no-underline';

/** Eine Antwort ist Fliesstext oder, wo sie aufzaehlt, eine kurze Liste */
const FAQS: { question: string; answer: ReactNode | string[] }[] = [
    {
        question: 'Ist Spesenfuchs wirklich kostenlos?',
        answer: 'Ja. Spesenfuchs kostet nichts – für alle Schiedsrichter in Thüringen, ohne versteckte Kosten ' +
            'und ohne Bezahlfunktionen.',
    },
    {
        question: 'Wer kann meine DFBnet-Zugangsdaten sehen?',
        answer: 'Dein DFBnet-Passwort liegt verschlüsselt auf dem Server und wird nur entschlüsselt, um deine Daten ' +
            'aus DFBnet abzurufen – nachts oder wenn du den Abruf selbst startest. In DFBnet wird dabei nichts ' +
            'verändert. Dein Spesenfuchs-Passwort wird nur als Hash gespeichert, übertragen wird ausschließlich ' +
            'über HTTPS, und nichts wird an Dritte weitergegeben.',
    },
    {
        question: 'Welche Daten liest Spesenfuchs aus DFBnet?',
        answer: [
            'Für die Abrechnung: Datum, Anstoß, Paarung, Spielklasse und Spielstätte sowie Name und Anschrift der angesetzten Unparteiischen.',
            'Nur zur Anzeige: Telefon und E-Mail des Gespanns – sie stehen in keinem Dokument.',
            'Reiter „Stammdaten“: deine eigenen DFBnet-Stammdaten samt Qualifikations-Maximum, die persönlichen Angaben verschlüsselt.',
            'Reiter „Saison“: deine geleiteten Spiele mit Ergebnis, Karten und Gespann, dazu Einsatzbilanz, Lehrabende und Leistungsprüfungen.',
            'Dein Passfoto wird nicht abgerufen.',
        ],
    },
    {
        question: 'Wie werden Pokal- und Freundschaftsspiele abgerechnet?',
        answer: 'Nach der TFV-Spesenordnung zählt beim Pokal die höchstklassige beteiligte Mannschaft, beim ' +
            'Freundschaftsspiel der Gastgeber. Im Herrenbereich schlägt Spesenfuchs die Vereine dafür in den ' +
            'Tabellen von Thüringenliga und Landesklasse nach (Reiter „Ligen“, von FUSSBALL.DE). Lässt sich ein ' +
            'Verein nicht sicher zuordnen, bleibt der Satz leer statt geraten.',
    },
    {
        question: 'Warum steht bei einem Spiel kein Betrag?',
        answer: 'Bei überregionalen Spielen wie der Oberliga und bei Spielen anderer Landesverbände gelten nicht ' +
            'die Sätze der TFV-Spesenordnung – dort trägt Spesenfuchs bewusst nichts ein. Dasselbe gilt, wenn sich ' +
            'bei einem Pokal- oder Freundschaftsspiel ein Verein nicht sicher zuordnen lässt. Den Betrag kannst du ' +
            'dann selbst im Word-Dokument ergänzen.',
    },
    {
        question: 'Muss ich die Fahrtkosten selbst eintragen?',
        answer: 'Ja, die Kilometer oder die Kosten für öffentliche Verkehrsmittel trägst du je Person im Rechner ' +
            'ein; Kilometer werden mit 0,30 € abgerechnet. Die Karte zeigt dir dazu die Anschriften des Gespanns ' +
            'und die Spielstätte.',
    },
    {
        question: 'Wann sind meine Abrechnungen da?',
        answer: 'Jede Nacht um 3 Uhr startet ein Abruf für alle Nutzer – deine Abrechnungen sind also meist ' +
            'fertig, bevor du sie brauchst. Einen Abruf auf Knopfdruck kannst du jederzeit selbst starten, er ' +
            'dauert je nach Anzahl der Spiele 1 bis 6 Minuten.',
    },
    {
        question: 'Kann ich die Dokumente nachträglich bearbeiten?',
        answer: 'Ja. Die Word-Dokumente kannst du nach dem Download mit Microsoft Word oder einem kompatiblen ' +
            'Programm beliebig anpassen.',
    },
    {
        question: 'Wie lösche ich meinen Account?',
        answer: (
            <>
                Schreib eine Mail an{' '}
                <a href="mailto:spesen-generator@jan-vogt.dev" className={ANTWORT_LINK}>
                    spesen-generator@jan-vogt.dev
                </a>{' '}
                – dann werden dein Konto und alle zugehörigen Daten gelöscht. Einzelheiten stehen in der{' '}
                <Link to="/datenschutz" className={ANTWORT_LINK}>Datenschutzerklärung</Link>.
            </>
        ),
    },
];

/** Inline-Style fuer die gestaffelte Verzoegerung eines [data-reveal]-Elements */
function verzoegerung(millisekunden: number): CSSProperties {
    return {'--reveal-delay': `${millisekunden}ms`} as CSSProperties;
}

/**
 * Spielfeld-Markierungen in Originalmassen (105 x 68 Meter). Die Strichstaerke
 * skaliert bewusst mit: in der gekippten Ebene werden die nahen Linien dadurch
 * breiter als die fernen, so wie auf einem echten Platz. Als Wasserzeichen
 * stoeren die gefuellten Punkte - sie sehen dort wie Flecken aus.
 */
function Spielfeld({className, proportional, ohnePunkte}: {
    className?: string;
    proportional?: boolean;
    ohnePunkte?: boolean;
}) {
    return (
        <svg
            viewBox="0 0 105 68"
            preserveAspectRatio={proportional ? undefined : 'none'}
            aria-hidden
            className={className}
            fill="none"
            stroke="currentColor"
            strokeWidth="0.3"
        >
            <rect x="0.2" y="0.2" width="104.6" height="67.6"/>
            <line x1="52.5" y1="0.2" x2="52.5" y2="67.8"/>
            <circle cx="52.5" cy="34" r="9.15"/>
            {/* Strafraum, Torraum und Torraumbogen, links */}
            <rect x="0.2" y="13.84" width="16.5" height="40.32"/>
            <rect x="0.2" y="24.84" width="5.5" height="18.32"/>
            <path d="M16.7 26.69 A 9.15 9.15 0 0 1 16.7 41.31"/>
            {/* dieselben Markierungen gespiegelt, rechts */}
            <rect x="88.3" y="13.84" width="16.5" height="40.32"/>
            <rect x="99.3" y="24.84" width="5.5" height="18.32"/>
            <path d="M88.3 41.31 A 9.15 9.15 0 0 1 88.3 26.69"/>
            {/* Anstoss- und Elfmeterpunkte */}
            {!ohnePunkte && (
                <g fill="currentColor" stroke="none">
                    <circle cx="52.5" cy="34" r="0.5"/>
                    <circle cx="11" cy="34" r="0.5"/>
                    <circle cx="94" cy="34" r="0.5"/>
                </g>
            )}
            {/* Eckviertel */}
            <path d="M1.2 0.2 A 1 1 0 0 1 0.2 1.2"/>
            <path d="M0.2 66.8 A 1 1 0 0 1 1.2 67.8"/>
            <path d="M103.8 67.8 A 1 1 0 0 1 104.8 66.8"/>
            <path d="M104.8 1.2 A 1 1 0 0 1 103.8 0.2"/>
        </svg>
    );
}

/** Das Zeichen: eine Schiedsrichterpfeife, passend zu Anpfiff und Abpfiff */
function Pfeife({className}: { className?: string }) {
    return (
        <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
            className={className}
        >
            <path d="M9 8h12v4h-6.34A6 6 0 1 1 9 8z"/>
            <circle cx="9" cy="14" r="1.6"/>
            <path d="M3.5 6.5 5.6 8.6"/>
        </svg>
    );
}

/** Zeichen und Wortmarke, oben und unten gleich */
function Marke({hell}: { hell: boolean }) {
    return (
        <span className="flex items-center gap-2.5">
            <span
                className={`grid size-8 place-items-center rounded-lg transition-colors ${
                    hell ? 'bg-flutlicht/15 text-flutlicht' : 'bg-primary text-primary-foreground'
                }`}
            >
                <Pfeife className="size-[1.1rem]"/>
            </span>
            <span
                className={`text-[15px] font-semibold tracking-tight whitespace-nowrap transition-colors ${
                    hell ? 'text-white' : 'text-foreground'
                }`}
            >
                Spesen<span className={hell ? 'text-flutlicht' : 'text-primary'}>fuchs</span>
            </span>
        </span>
    );
}

/** Hoehe der Kopfzeile in px (h-14) */
const KOPFHOEHE = 56;

/**
 * Ob unter der Kopfzeile gerade ein Nacht-Abschnitt liegt (alles mit
 * data-nacht). Beobachtet wird nur der Streifen hinter der Kopfzeile: der
 * untere Rand des Beobachters rueckt dafuer bis auf KOPFHOEHE an den oberen
 * heran. Der Wert haengt an der Fensterhoehe und wird deshalb bei jeder
 * Groessenaenderung neu gesetzt - am Handy auch, wenn die Adressleiste
 * ein- oder ausfaehrt.
 */
function useUnterKopfNacht(): boolean {
    const [nacht, setNacht] = useState(true);

    useEffect(() => {
        const abschnitte = Array.from(document.querySelectorAll('[data-nacht]'));
        if (!abschnitte.length || !('IntersectionObserver' in window)) {
            return;
        }

        const darunter = new Set<Element>();
        let beobachter: IntersectionObserver | undefined;

        const aufbauen = () => {
            beobachter?.disconnect();
            darunter.clear();
            beobachter = new IntersectionObserver(
                (eintraege) => {
                    eintraege.forEach((eintrag) => {
                        if (eintrag.isIntersecting) {
                            darunter.add(eintrag.target);
                        } else {
                            darunter.delete(eintrag.target);
                        }
                    });
                    setNacht(darunter.size > 0);
                },
                {rootMargin: `0px 0px ${KOPFHOEHE - window.innerHeight}px 0px`},
            );
            abschnitte.forEach((abschnitt) => beobachter?.observe(abschnitt));
        };

        aufbauen();
        window.addEventListener('resize', aufbauen);
        return () => {
            beobachter?.disconnect();
            window.removeEventListener('resize', aufbauen);
        };
    }, []);

    return nacht;
}

/**
 * Kopfzeile. Ganz oben ist sie durchsichtig. Liegt ein Nacht-Abschnitt
 * unter ihr (Hero, Spielablauf, Abschluss), wird sie dunkles Glas - ein
 * heller Balken ueber dem dunklen Grund braeche Stimmung und Kontrast. Ueber
 * den hellen Abschnitten legt sie sich auf die Flaeche der Anwendung.
 *
 * Am Handy steht rechts nur "Anmelden": die Hauptaktion hat dort der Hero
 * und danach die Leiste am unteren Rand, in Reichweite des Daumens.
 */
function Kopfzeile({angemeldet}: { angemeldet: boolean }) {
    const [gescrollt, setGescrollt] = useState(false);
    const dunkel = useUnterKopfNacht();

    useEffect(() => {
        const pruefen = () => setGescrollt(window.scrollY > 24);
        pruefen();
        window.addEventListener('scroll', pruefen, {passive: true});
        return () => window.removeEventListener('scroll', pruefen);
    }, []);

    const flaeche = !gescrollt
        ? 'border-transparent'
        : dunkel
            ? 'border-white/10 bg-[oklch(0.17_0.028_158/0.72)] backdrop-blur-md'
            : 'border-border bg-background/80 backdrop-blur-md';

    return (
        <header className={`fixed inset-x-0 top-0 z-50 border-b transition-colors duration-300 ${flaeche}`}>
            <div className={`${RAHMEN} flex h-14 items-center justify-between`}>
                <Link to="/" aria-label="Spesenfuchs, zur Startseite" className="-m-1 rounded-lg p-1">
                    <Marke hell={dunkel}/>
                </Link>
                <nav className="flex items-center gap-1 sm:gap-2">
                    {angemeldet ? (
                        <Button
                            asChild
                            size="sm"
                            className={`h-10 px-4 sm:h-9 ${dunkel ? 'bg-flutlicht text-nacht hover:bg-flutlicht/90' : ''}`}
                        >
                            <Link to="/dashboard">
                                Zum Dashboard
                                <ArrowRight/>
                            </Link>
                        </Button>
                    ) : (
                        <>
                            <Button
                                asChild
                                variant="ghost"
                                size="sm"
                                className={`h-11 px-3 text-sm sm:h-9 ${
                                    dunkel ? 'text-white/80 hover:bg-white/10 hover:text-white' : 'text-foreground/75'
                                }`}
                            >
                                <Link to="/login">Anmelden</Link>
                            </Button>
                            <Button
                                asChild
                                size="sm"
                                className={`hidden h-9 px-4 sm:inline-flex ${
                                    dunkel ? 'bg-flutlicht text-nacht hover:bg-flutlicht/90' : ''
                                }`}
                            >
                                <Link to="/register">Kostenlos starten</Link>
                            </Button>
                        </>
                    )}
                </nav>
            </div>
        </header>
    );
}

/**
 * Die Buehne rechts im Hero, ab md: hinten das Fenster mit den Ansetzungen,
 * vorne die fertige Abrechnung, daneben die Karte zur Anfahrt. Die Ebenen
 * verschieben sich leicht gegeneinander, wenn der Mauszeiger sich bewegt -
 * gesteuert ueber --zx/--zy am Rahmen, damit React dafuer nicht neu rendert.
 *
 * Die Abrechnung haengt oben an einer festen Hoehe statt unten am Rahmen:
 * ihre Oberkante liegt so knapp unter der Trennlinie nach der zweiten
 * Ansetzung (Kopf 38 px, Zeilen je 54 px, also bei 146 px), dass sie auch
 * beim Schweben keine Zeile mitten durch den Text schneidet. Zwischen lg und
 * xl ist die Spalte zu schmal fuer drei Ebenen - dort entfaellt die Karte
 * und die Abrechnung wird breiter.
 */
function Buehne({rahmen}: { rahmen: RefObject<HTMLDivElement | null> }) {
    const ebene = (tiefe: number): CSSProperties => ({
        transform: `translate3d(calc(var(--zx, 0) * ${tiefe}px), calc(var(--zy, 0) * ${tiefe * 0.8}px), 0)`,
    });

    return (
        <div
            ref={rahmen}
            className="relative mx-auto h-[30rem] w-full max-w-[40rem] select-none [perspective:1400px]"
        >
            <div
                className="absolute inset-0 transition-transform duration-500 ease-out"
                style={{transform: 'rotateX(calc(var(--zy, 0) * -5deg)) rotateY(calc(var(--zx, 0) * 7deg))'}}
            >
                <div className="absolute top-0 right-0 w-[84%] transition-transform duration-500 ease-out" style={ebene(-14)}>
                    <Spieleliste/>
                </div>

                <div className="absolute right-0 bottom-3 z-10 w-[34%] transition-transform duration-500 ease-out lg:max-xl:hidden" style={ebene(22)}>
                    <div className="spesen-schweben" style={{animationDelay: '-3s'}}>
                        <Anfahrtschip/>
                    </div>
                </div>

                <div className="absolute top-[9.5rem] left-0 z-20 w-[72%] transition-transform duration-500 ease-out lg:max-xl:w-[82%]" style={ebene(10)}>
                    <div className="spesen-schweben">
                        <Abrechnungskarte/>
                    </div>
                </div>
            </div>
        </div>
    );
}

/**
 * Die Kennzahlen als Anzeigetafel am Fuss des Hero. Die Zahl der erfassten
 * Spiele erscheint nur, wenn es eine gibt - ein Strich oder eine Null saehe
 * nach kaputt aus. Gezaehlt wird erst, wenn die Tafel im Bild ist.
 */
function Anzeigetafel() {
    const tafel = useRef<HTMLDivElement>(null);
    const [spiele, setSpiele] = useState<number | 'laedt' | 'fehlt'>('laedt');
    const gesehen = useImBild(tafel, {einmal: true, anfang: false});
    const gezaehlt = useCountUp(gesehen && typeof spiele === 'number' ? spiele : null);

    useEffect(() => {
        api.get('/api/stats/public')
            .then((response) => {
                const anzahl = Number(response.data?.matches_total);
                setSpiele(Number.isFinite(anzahl) && anzahl > 0 ? anzahl : 'fehlt');
            })
            .catch(() => setSpiele('fehlt'));
    }, []);

    const felder: { wert: ReactNode; kurz: string; lang: string }[] = [
        {wert: '03:00', kurz: 'Abruf jede Nacht', lang: 'Uhr – automatischer Abruf, jede Nacht'},
        {wert: '0 €', kurz: 'für alle SR', lang: 'kostenlos für alle SR in Thüringen'},
    ];
    if (spiele !== 'fehlt') {
        felder.push({
            wert: spiele === 'laedt'
                ? <span className="inline-block h-[0.8em] w-[2.5em] rounded-md bg-white/10 align-middle"/>
                : gezaehlt.toLocaleString('de-DE'),
            kurz: 'Spiele erfasst',
            lang: 'Spiele bisher erfasst',
        });
    }

    return (
        <div ref={tafel} className="relative border-t border-white/10 bg-[oklch(0.145_0.026_158/0.88)]">
            <div className={`${RAHMEN} grid ${felder.length === 3 ? 'grid-cols-3' : 'grid-cols-2'} divide-x divide-white/10`}>
                {felder.map((feld) => (
                    <div key={feld.kurz} className="px-1 py-4 text-center sm:py-7 lg:py-5">
                        <p className="spesen-leuchtziffer text-2xl font-semibold tracking-tight text-flutlicht tabular-nums sm:text-4xl lg:text-5xl">
                            {feld.wert}
                        </p>
                        <p className="mt-1 text-xs text-white/60 sm:text-sm">
                            <span className="sm:hidden">{feld.kurz}</span>
                            <span className="hidden sm:inline">{feld.lang}</span>
                        </p>
                    </div>
                ))}
            </div>
        </div>
    );
}

function Satzchip({satz}: { satz: (typeof SPESENSAETZE)[number] }) {
    return (
        <span className="flex shrink-0 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[13px] whitespace-nowrap text-white/60 sm:py-1 sm:text-xs">
            <span className="font-medium text-white/90">{satz.klasse}</span>
            <span className="text-flutlicht tabular-nums">{satz.sr}</span>
            <span className="text-white/30">/</span>
            <span className="tabular-nums">{satz.sra}</span>
        </span>
    );
}

/**
 * Die Saetze der Spesenordnung. Am Handy eine Reihe zum Wischen - ein
 * Laufband liesse sich dort weder anhalten noch in Ruhe lesen. Ab sm laeuft
 * es als Band mit fester Quellenangabe links und einem Knopf zum Anhalten.
 * Die zweite Kopie des Bandes gibt es nur fuers Auge, Screenreader lesen die
 * Liste einmal. Ohne Bewegung bricht das Band um, statt abgeschnitten
 * stehen zu bleiben (siehe index.css).
 */
function Satzband() {
    const [angehalten, setAngehalten] = useState(false);

    return (
        <div className="relative border-t border-white/10 bg-[oklch(0.145_0.026_158/0.88)]">
            {/* Handy */}
            <div className="py-3 sm:hidden">
                <p className="px-4 text-[11px] font-medium tracking-wide text-white/60">{QUELLE}</p>
                <ul className="mt-2 flex snap-x snap-mandatory scroll-px-4 gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                    {SPESENSAETZE.map((satz) => (
                        <li key={satz.klasse} className="snap-start">
                            <Satzchip satz={satz}/>
                        </li>
                    ))}
                </ul>
            </div>

            {/* ab sm */}
            <div className="hidden items-stretch pr-[env(safe-area-inset-right)] sm:flex">
                <p className="flex shrink-0 items-center border-r border-white/10 pr-6 pl-[max(1.5rem,env(safe-area-inset-left))] text-xs font-medium text-white/60 lg:pr-10 lg:pl-10">
                    {QUELLE}
                </p>
                <div className="relative min-w-0 flex-1 overflow-hidden py-3">
                    <div className="spesen-laufband-rand pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-[oklch(0.145_0.026_158)] to-transparent"/>
                    <div className="spesen-laufband-rand pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-[oklch(0.145_0.026_158)] to-transparent"/>
                    <div className={`spesen-laufband flex w-max ${angehalten ? 'is-angehalten' : ''}`}>
                        {[0, 1].map((durchlauf) => (
                            <ul
                                key={durchlauf}
                                aria-hidden={durchlauf === 1 || undefined}
                                className="spesen-laufband-gruppe flex shrink-0 gap-3 pr-3"
                            >
                                {SPESENSAETZE.map((satz) => (
                                    <li key={satz.klasse}>
                                        <Satzchip satz={satz}/>
                                    </li>
                                ))}
                            </ul>
                        ))}
                    </div>
                </div>
                <button
                    type="button"
                    onClick={() => setAngehalten((wert) => !wert)}
                    aria-label={angehalten ? 'Laufband weiterlaufen lassen' : 'Laufband anhalten'}
                    className="grid w-12 shrink-0 place-items-center border-l border-white/10 text-white/60 transition-colors hover:bg-white/5 hover:text-white motion-reduce:hidden"
                >
                    {angehalten ? <Play className="size-4"/> : <Pause className="size-4"/>}
                </button>
            </div>
        </div>
    );
}

/** Der dunkle Block ganz oben: Versprechen, Beispiel, Zahlen, Spesensaetze */
function Hero({angemeldet, ctaRef}: {
    angemeldet: boolean;
    ctaRef: RefObject<HTMLDivElement | null>;
}) {
    const buehne = useRef<HTMLDivElement>(null);

    // Die Buehne neigt sich ein Stueck zum Mauszeiger. Auf Touchgeraeten
    // kommt kein mousemove an, dort bleibt sie schlicht stehen.
    const zeigerBewegt = (ereignis: React.MouseEvent<HTMLElement>) => {
        const element = buehne.current;
        if (!element || magKeineBewegung()) {
            return;
        }
        const kasten = ereignis.currentTarget.getBoundingClientRect();
        element.style.setProperty('--zx', ((ereignis.clientX - kasten.left) / kasten.width - 0.5).toFixed(3));
        element.style.setProperty('--zy', ((ereignis.clientY - kasten.top) / kasten.height - 0.5).toFixed(3));
    };

    const zeigerWeg = () => {
        buehne.current?.style.setProperty('--zx', '0');
        buehne.current?.style.setProperty('--zy', '0');
    };

    return (
        <section
            data-nacht
            className="spesen-nacht relative isolate flex flex-col overflow-hidden text-white lg:min-h-[100svh]"
            onMouseMove={zeigerBewegt}
            onMouseLeave={zeigerWeg}
        >
            {/* Spielfeld, in die Tiefe gekippt */}
            <div aria-hidden className="spesen-feld pointer-events-none absolute inset-x-0 bottom-0 h-[65%]">
                <div className="absolute inset-0">
                    <div className="spesen-rasen absolute inset-0"/>
                    <Spielfeld className="absolute inset-x-[6%] inset-y-[8%] h-[84%] w-[88%] text-white/20"/>
                </div>
            </div>

            {/* Flutlicht von oben und Filmkorn darueber */}
            <div aria-hidden className="spesen-strahl spesen-flutlicht pointer-events-none absolute inset-0"/>
            <div aria-hidden className="spesen-koerner pointer-events-none absolute inset-0"/>

            {/* grid-cols-1 haelt die Spalte auf Bildschirmbreite; ein Raster ohne
                Spalten waechst sonst mit dem breitesten Inhalt und schneidet bei
                320 px den Text ab. */}
            <div className={`${RAHMEN} relative grid flex-1 grid-cols-1 items-center gap-12 pt-24 pb-12 sm:pt-32 md:gap-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.02fr)] lg:content-center lg:gap-10 lg:pt-20 lg:pb-10 xl:gap-16`}>
                <div className="text-center lg:text-left">
                    <p
                        className="spesen-aufsteigen mb-5 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-medium text-white/80 backdrop-blur"
                        style={{animationDelay: '60ms'}}
                    >
                        <span className="relative grid size-1.5 place-items-center">
                            <span className="spesen-puls absolute size-1.5 rounded-full bg-flutlicht"/>
                            <span className="size-1.5 rounded-full bg-flutlicht"/>
                        </span>
                        <span className="sm:hidden">Für Schiedsrichter im TFV</span>
                        <span className="hidden sm:inline">Für Schiedsrichter des Thüringer Fußball-Verbandes</span>
                    </p>

                    <h1 className="text-[clamp(2.4rem,1rem+3.9vw,5.75rem)] leading-[1.02] font-semibold tracking-[-0.035em]">
                        {/* Jede Zeile faehrt aus ihrer eigenen Zeile herauf, deshalb
                            der Ausschnitt je Zeile statt einer Animation auf der
                            ganzen Ueberschrift. */}
                        <span className="block overflow-hidden pb-2 -mb-2">
                            <span className="spesen-zeile block" style={{animationDelay: '120ms'}}>
                                Abpfiff für den
                            </span>
                        </span>
                        <span className="block overflow-hidden pb-2 -mb-2">
                            <span className="spesen-zeile block" style={{animationDelay: '240ms'}}>
                                <span className="spesen-leuchtschrift text-flutlicht">Papierkram</span>.
                            </span>
                        </span>
                    </h1>

                    <p
                        className="spesen-aufsteigen mx-auto mt-5 max-w-xl text-[17px] leading-relaxed text-white/70 sm:mt-6 sm:text-lg lg:mx-0"
                        style={{animationDelay: '380ms'}}
                    >
                        Deine Spesenabrechnungen entstehen jede Nacht aus deinen DFBnet-Ansetzungen.
                        Satz, Gespann und Spielstätte stehen schon drin – du trägst nur noch die Kilometer ein.
                    </p>

                    <div
                        ref={ctaRef}
                        className="spesen-aufsteigen mt-7 flex flex-col items-center gap-3 sm:mt-8 sm:flex-row sm:justify-center lg:justify-start"
                        style={{animationDelay: '460ms'}}
                    >
                        <Button
                            asChild
                            size="lg"
                            className="h-12 w-full bg-flutlicht px-6 text-base text-nacht shadow-lg shadow-flutlicht/25 hover:bg-flutlicht/90 sm:h-11 sm:w-auto sm:text-[15px]"
                        >
                            <Link to={angemeldet ? '/dashboard' : '/register'}>
                                {angemeldet ? 'Zum Dashboard' : 'Kostenlos starten'}
                                <ArrowRight className="size-4"/>
                            </Link>
                        </Button>
                        {!angemeldet && (
                            <>
                                <Button
                                    asChild
                                    size="lg"
                                    variant="secondary"
                                    className="hidden h-11 border border-white/20 bg-white/10 px-6 text-[15px] text-white hover:bg-white/20 sm:inline-flex"
                                >
                                    <Link to="/login">Anmelden</Link>
                                </Button>
                                <Link
                                    to="/login"
                                    className="inline-flex min-h-11 items-center px-3 text-sm text-white/70 underline-offset-4 hover:text-white hover:underline sm:hidden"
                                >
                                    Schon dabei?&nbsp;<span className="font-medium text-white">Anmelden</span>
                                </Link>
                            </>
                        )}
                    </div>

                    <ul
                        className="spesen-aufsteigen mt-5 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-sm text-white/65 sm:mt-8 sm:gap-x-5 lg:justify-start"
                        style={{animationDelay: '540ms'}}
                    >
                        {['Kostenlos', 'Ohne Installation', 'Verschlüsselt'].map((eintrag) => (
                            <li key={eintrag} className="flex items-center gap-1.5">
                                <CheckCircle2 className="size-4 text-flutlicht"/>
                                {eintrag}
                            </li>
                        ))}
                    </ul>
                </div>

                <div className="spesen-aufsteigen relative w-full" style={{animationDelay: '520ms'}}>
                    {/* Handy: nur die Abrechnung, die Buehne waere dort zu klein */}
                    <div className="mx-auto w-full max-w-md md:hidden">
                        <div className="spesen-schweben">
                            <Abrechnungskarte/>
                        </div>
                    </div>
                    <div className="hidden md:block">
                        <Buehne rahmen={buehne}/>
                    </div>
                </div>
            </div>

            <Anzeigetafel/>
            <Satzband/>
            {/* Leuchtende Seitenlinie als Grenze zum hellen Teil */}
            <div aria-hidden className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-flutlicht/50 to-transparent"/>
        </section>
    );
}

/** Rahmen einer dunklen Kachel, mit dem Rasen des Hero als Grund */
function NachtFlaeche({children, className = ''}: { children: ReactNode; className?: string }) {
    return (
        <div className={`spesen-nacht relative isolate h-full overflow-hidden rounded-2xl border border-white/10 p-5 text-white sm:p-6 ${className}`}>
            <div aria-hidden className="spesen-feld pointer-events-none absolute inset-x-0 bottom-0 h-3/4">
                <div className="absolute inset-0">
                    <div className="spesen-rasen absolute inset-0"/>
                </div>
            </div>
            {children}
        </div>
    );
}

function Kachelkopf({icon: Icon, title, hell}: { icon: LucideIcon; title: string; hell?: boolean }) {
    return (
        <div className="flex items-center gap-3">
            <span
                className={`grid size-9 shrink-0 place-items-center rounded-xl ${
                    hell ? 'bg-flutlicht/15 text-flutlicht' : 'bg-primary/10 text-primary'
                }`}
            >
                <Icon className="size-[1.1rem]"/>
            </span>
            <h3 className="font-medium">{title}</h3>
        </div>
    );
}

/**
 * Die Nacht-Kachel mit der Uhr: der Lauf um 3 Uhr. Am Handy steht die Uhr
 * klein neben der Ueberschrift, damit der Text die ganze Breite bekommt -
 * daneben gequetscht brach er bei 320 px in acht Zeilen um.
 */
function LaufKachel() {
    return (
        <NachtFlaeche className="flex items-center gap-8">
            <div className="relative min-w-0 flex-1">
                <div className="flex items-center justify-between gap-3">
                    <Kachelkopf icon={MoonStar} title="Läuft, während du schläfst" hell/>
                    <Nachtuhr className="size-14 shrink-0 sm:hidden"/>
                </div>
                <p className="mt-3 max-w-md text-sm leading-relaxed text-white/65">
                    Jede Nacht um 3 Uhr holt Spesenfuchs deine neuen Ansetzungen aus DFBnet und legt die
                    Abrechnungen an. Eilig? Dann startest du den Abruf selbst.
                </p>
            </div>
            <div className="relative hidden shrink-0 flex-col items-center gap-2 sm:flex">
                <Nachtuhr className="size-28 lg:size-36"/>
                <span className="text-[11px] tracking-wide text-white/55 tabular-nums">03:00 Uhr</span>
            </div>
        </NachtFlaeche>
    );
}

/** Die Nacht-Kachel mit der Saison */
function SaisonKachel() {
    return (
        <NachtFlaeche className="grid gap-5 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] md:items-center md:gap-8">
            <div className="relative">
                <Kachelkopf icon={ChartColumn} title="Deine Saison in Zahlen" hell/>
                <p className="mt-3 text-sm leading-relaxed text-white/65">
                    Alle geleiteten Spiele je Saison mit Ergebnis, Karten und Gespann – dazu deine
                    Einsatzbilanz als SR und SRA, Lehrabende und Leistungsprüfung.
                </p>
            </div>
            <div className="relative">
                <Saisontafel/>
            </div>
        </NachtFlaeche>
    );
}

/** Eine helle Kachel mit Beleg oben und Text darunter */
function Funktionskachel({funktion}: { funktion: Funktion }) {
    const zeigerBewegt = (ereignis: React.MouseEvent<HTMLDivElement>) => {
        const kasten = ereignis.currentTarget.getBoundingClientRect();
        ereignis.currentTarget.style.setProperty('--mx', `${ereignis.clientX - kasten.left}px`);
        ereignis.currentTarget.style.setProperty('--my', `${ereignis.clientY - kasten.top}px`);
    };

    return (
        <div
            onMouseMove={zeigerBewegt}
            className="spesen-glanz spesen-kachel group relative isolate flex h-full flex-col overflow-hidden rounded-2xl border bg-card p-4 transition duration-300 hover:border-primary/30 hover:shadow-xl hover:shadow-primary/5 motion-safe:hover:-translate-y-1 sm:p-5"
        >
            {/* @container: die Belege richten sich nach der Breite der Kachel,
                nicht nach der des Fensters (siehe SCHMAL in Schaufenster.tsx) */}
            <div className="@container relative flex h-44 items-center justify-center overflow-hidden rounded-xl border bg-muted/40 p-3 dark:bg-white/[0.025]">
                {funktion.bild}
            </div>
            <div className="relative mt-4 px-1">
                <Kachelkopf icon={funktion.icon} title={funktion.title}/>
                <p className="mt-2.5 text-sm leading-relaxed text-muted-foreground">
                    {funktion.description}
                </p>
            </div>
        </div>
    );
}

/**
 * Die Funktionen als Aufstellung. Ab xl ein Raster in 2 + 1 + 1 und
 * 1 + 1 + 2, dunkel oben links und unten rechts; zwischen sm und xl zwei
 * Spalten, in vier waeren die hellen Kacheln dort zu schmal fuer ihre Belege. Am Handy stehen die zwei
 * dunklen Kacheln breit, die vier hellen dazwischen in einer Reihe zum
 * Wischen - sechs gestapelte Kaesten waeren fast zwei Bildschirme Scrollen.
 * Ab sm loest sich die Reihe per display: contents ins Raster auf.
 */
function Aufstellung() {
    const reihe = useRef<HTMLDivElement>(null);
    const [aktiv, setAktiv] = useState(0);

    const gewischt = () => {
        const element = reihe.current;
        if (!element) {
            return;
        }
        const weg = element.scrollWidth - element.clientWidth;
        setAktiv(weg > 0 ? Math.round((element.scrollLeft / weg) * (FUNKTIONEN.length - 1)) : 0);
    };

    return (
        <section className="spesen-band relative isolate overflow-hidden py-16 sm:py-24 lg:py-28">
            <div aria-hidden className="spesen-uebergang pointer-events-none absolute inset-x-0 top-0 h-64"/>
            <div className={`${RAHMEN} relative`}>
                <div data-reveal className="mb-10 grid gap-4 sm:mb-12 lg:grid-cols-2 lg:items-end lg:gap-16">
                    <div>
                        <p className="mb-2 text-xs font-medium tracking-wide text-primary uppercase">Aufstellung</p>
                        <h2 className="text-[1.75rem] leading-tight font-semibold tracking-tight text-balance sm:text-4xl">
                            Mehr als eine Abrechnung
                        </h2>
                    </div>
                    {/* foreground/70 statt muted: auf dem grauen Band kaeme muted nur auf 4,3:1 */}
                    <p className="max-w-xl text-[15px] leading-relaxed text-foreground/70 sm:text-base lg:justify-self-end">
                        Rund um jede Ansetzung liegt alles an einem Ort: Anfahrt, Einstufung, Dokumente, deine
                        Stammdaten und die ganze Saison – aus deinen DFBnet-Daten, ohne Abtippen.
                    </p>
                </div>

                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    <div data-reveal className="sm:col-span-2">
                        <LaufKachel/>
                    </div>

                    <div
                        ref={reihe}
                        onScroll={gewischt}
                        data-reveal
                        className="spesen-wisch -mx-4 flex snap-x snap-mandatory scroll-px-4 gap-3 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:contents [&::-webkit-scrollbar]:hidden"
                    >
                        {FUNKTIONEN.map((funktion, index) => (
                            <div
                                key={funktion.title}
                                data-reveal
                                style={verzoegerung(70 + index * 70)}
                                className="w-[84%] shrink-0 snap-start sm:w-auto"
                            >
                                <Funktionskachel funktion={funktion}/>
                            </div>
                        ))}
                    </div>

                    <div aria-hidden className="-mt-1 flex justify-center gap-1.5 sm:hidden">
                        {FUNKTIONEN.map((funktion, index) => (
                            <span
                                key={funktion.title}
                                className={`h-1.5 rounded-full transition-all duration-300 ${
                                    index === aktiv ? 'w-5 bg-primary' : 'w-1.5 bg-foreground/20'
                                }`}
                            />
                        ))}
                    </div>

                    <div data-reveal style={verzoegerung(140)} className="sm:col-span-2">
                        <SaisonKachel/>
                    </div>
                </div>
            </div>
        </section>
    );
}

/**
 * Ein Stueck der Bahn zwischen zwei Ziffern, senkrecht oder waagerecht. Am
 * Kopf der Fuellung laeuft ein Ball mit, damit zu sehen ist, wo die Bahn
 * gerade steht.
 */
function Bahnstueck({fuellung, senkrecht, className}: { fuellung: number; senkrecht?: boolean; className: string }) {
    return (
        <span aria-hidden className={`absolute bg-white/12 ${className}`}>
            <span
                className={`absolute bg-flutlicht shadow-[0_0_12px] shadow-flutlicht/60 ${
                    senkrecht ? 'inset-x-0 top-0' : 'inset-y-0 left-0'
                }`}
                style={senkrecht ? {height: `${fuellung * 100}%`} : {width: `${fuellung * 100}%`}}
            />
            {fuellung > 0 && fuellung < 1 && (
                <span
                    className={`spesen-ball absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white ${
                        senkrecht ? 'left-1/2' : 'top-1/2'
                    }`}
                    style={senkrecht ? {top: `${fuellung * 100}%`} : {left: `${fuellung * 100}%`}}
                />
            )}
        </span>
    );
}

/**
 * Die vier Schritte auf einer Bahn, die beim Scrollen mitlaeuft: untereinander
 * senkrecht, ab lg waagerecht zwischen den Ziffern. Jeder Schritt zeichnet
 * sein Stueck bis zur naechsten Ziffer selbst - so endet die Bahn genau an
 * der letzten statt irgendwo unter deren Text. Der Abschnitt ist ein
 * Nacht-Band: hell, dunkel, hell, dunkel statt dreier heller Bloecke
 * hintereinander.
 */
function Spielablauf() {
    const bereich = useRef<HTMLDivElement>(null);
    const fortschritt = useScrollProgress(bereich);
    const stufe = fortschritt * SCHRITTE.length;

    return (
        <section data-nacht className="spesen-nacht relative isolate overflow-hidden py-16 text-white sm:py-24 lg:py-28">
            <div aria-hidden className="pointer-events-none absolute inset-0 hidden place-items-center lg:grid">
                <Spielfeld proportional ohnePunkte className="spesen-wasserzeichen w-[min(94%,86rem)] text-white/[0.07]"/>
            </div>
            <div aria-hidden className="spesen-koerner pointer-events-none absolute inset-0"/>

            <div className={`${RAHMEN} relative`}>
                <div data-reveal className="mb-10 max-w-xl sm:mb-14">
                    <p className="mb-2 text-xs font-medium tracking-wide text-flutlicht uppercase">Spielablauf</p>
                    <h2 className="text-[1.75rem] leading-tight font-semibold tracking-tight text-balance sm:text-4xl">
                        In vier Schritten zur Abrechnung
                    </h2>
                </div>

                <div ref={bereich} className="relative grid gap-9 lg:grid-cols-4 lg:gap-8">
                    {SCHRITTE.map((schritt, index) => {
                        // Die Ziffer leuchtet auf, wenn der Ball des Stuecks davor
                        // bei ihr ankommt (das Stueck fuellt sich von index - 0.5
                        // bis index + 0.5).
                        const erreicht = stufe > index + 0.45;
                        const fuellung = Math.min(1, Math.max(0, stufe - (index + 0.5)));
                        const letzter = index === SCHRITTE.length - 1;

                        return (
                            <div
                                key={schritt.title}
                                data-reveal
                                style={verzoegerung(index * 90)}
                                className="relative pl-16 lg:pl-0"
                            >
                                {/* Senkrecht, solange die Schritte untereinander stehen:
                                    von der Ziffer bis zur naechsten, ueber den Abstand
                                    gap-9 hinweg. */}
                                {!letzter && (
                                    <Bahnstueck
                                        senkrecht
                                        fuellung={fuellung}
                                        className="top-11 -bottom-9 left-[1.375rem] w-px lg:hidden"
                                    />
                                )}
                                <div className="absolute top-0 left-0 lg:static lg:mb-5 lg:flex lg:items-center lg:gap-3">
                                    {/* Deckend, damit Bahn und Ball hinter der Ziffer verschwinden */}
                                    <span
                                        className={`relative grid size-11 shrink-0 place-items-center rounded-full border font-mono text-sm font-semibold transition-all duration-500 ${
                                            erreicht
                                                ? 'border-flutlicht bg-flutlicht text-nacht shadow-[0_0_24px] shadow-flutlicht/40'
                                                : 'border-white/15 bg-[oklch(0.21_0.026_158)] text-white/60'
                                        }`}
                                    >
                                        {String(index + 1).padStart(2, '0')}
                                    </span>
                                    {!letzter && (
                                        <span className="relative hidden h-px flex-1 lg:block">
                                            <Bahnstueck fuellung={fuellung} className="inset-0"/>
                                        </span>
                                    )}
                                </div>
                                <p className="font-mono text-[11px] tracking-widest text-flutlicht/80 uppercase">
                                    {schritt.phase}
                                </p>
                                <h3 className="mt-1 text-lg font-medium">{schritt.title}</h3>
                                <p className="mt-1.5 text-sm leading-relaxed text-white/65">
                                    {schritt.description}
                                </p>
                                <span className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-white/15 px-2.5 py-1 text-xs text-white/70">
                                    <Clock className="size-3.5 text-flutlicht"/>
                                    {schritt.chip}
                                </span>
                            </div>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}

/** Was mit den Daten passiert - die groesste Huerde vor der Registrierung */
function Fairplay() {
    return (
        <section className="relative isolate overflow-hidden py-16 sm:py-24">
            <div aria-hidden className="spesen-uebergang pointer-events-none absolute inset-x-0 top-0 h-64"/>
            <div className={`${RAHMEN} relative grid gap-10 lg:grid-cols-[minmax(0,0.75fr)_minmax(0,1.25fr)] lg:gap-16`}>
                <div data-reveal>
                    <p className="mb-2 text-xs font-medium tracking-wide text-primary uppercase">Fairplay</p>
                    <h2 className="text-[1.75rem] leading-tight font-semibold tracking-tight text-balance sm:text-4xl">
                        Fair zu deinen Daten
                    </h2>
                    <p className="mt-4 max-w-md text-[15px] leading-relaxed text-muted-foreground sm:text-base">
                        Du gibst Spesenfuchs deinen DFBnet-Zugang. Dafür bekommst du klare Zusagen.
                    </p>
                    <Link
                        to="/datenschutz"
                        className="mt-4 inline-flex min-h-11 items-center gap-1.5 text-sm font-medium text-primary underline-offset-4 hover:underline"
                    >
                        Zur Datenschutzerklärung
                        <ArrowRight className="size-4"/>
                    </Link>
                </div>

                <ul className="grid gap-3 sm:grid-cols-2 sm:gap-4">
                    {FAIRPLAY.map((eintrag, index) => (
                        <li
                            key={eintrag.title}
                            data-reveal
                            style={verzoegerung(index * 70)}
                            className="flex gap-4 rounded-2xl border bg-card p-4 sm:p-5"
                        >
                            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
                                <eintrag.icon className="size-5"/>
                            </span>
                            <div>
                                <h3 className="font-medium">{eintrag.title}</h3>
                                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{eintrag.description}</p>
                            </div>
                        </li>
                    ))}
                </ul>
            </div>
        </section>
    );
}

function Fragen() {
    return (
        // overflow-clip statt overflow-hidden: schneidet das Wasserzeichen
        // genauso ab, macht den Abschnitt aber nicht zum Scroll-Container -
        // sonst griffe das sticky der linken Spalte nicht.
        <section className="spesen-band relative isolate overflow-clip border-y py-16 sm:py-24 lg:py-28">
            {/* Spielfeld als Wasserzeichen, sehr blass und erst ab lg - schmal
                blieben davon nur einzelne Striche, die wie verrutschte Linien
                aussehen. */}
            <div aria-hidden className="pointer-events-none absolute inset-0 hidden place-items-center lg:grid">
                <Spielfeld
                    proportional
                    ohnePunkte
                    className="spesen-wasserzeichen w-[min(92%,80rem)] text-foreground/[0.06]"
                />
            </div>

            <div className={`${RAHMEN} relative grid gap-10 lg:grid-cols-[minmax(0,0.75fr)_minmax(0,1.25fr)] lg:gap-16`}>
                <div data-reveal className="lg:sticky lg:top-24 lg:self-start">
                    <p className="mb-2 text-xs font-medium tracking-wide text-primary uppercase">Häufige Fragen</p>
                    <h2 className="text-[1.75rem] leading-tight font-semibold tracking-tight text-balance sm:text-4xl">
                        Fragen & Antworten
                    </h2>
                    <p className="mt-4 max-w-md text-[15px] leading-relaxed text-foreground/70 sm:text-base">
                        Etwas offen geblieben oder einen Fehler gefunden? Schreib mir einfach, ich antworte
                        selbst. Angemeldet geht es auch über den Reiter „Fehler melden“.
                    </p>
                    <a
                        href="mailto:spesen-generator@jan-vogt.dev"
                        className="mt-5 inline-flex max-w-full items-center gap-2 rounded-xl border bg-card px-4 py-3 text-sm font-medium transition-colors hover:border-primary/30 hover:text-primary"
                    >
                        <Mail className="size-4 shrink-0 text-primary"/>
                        <span className="truncate">spesen-generator@jan-vogt.dev</span>
                    </a>
                </div>

                {/* Eine Liste statt einzelner Karten: die Fragen gehoeren zusammen */}
                <div data-reveal className="divide-y overflow-hidden rounded-2xl border bg-card">
                    {FAQS.map((faq, index) => (
                        <details key={faq.question} className="group">
                            <summary className="flex min-h-16 cursor-pointer list-none items-center gap-4 px-5 py-4 [&::-webkit-details-marker]:hidden">
                                <span className="w-5 shrink-0 font-mono text-xs text-muted-foreground transition-colors group-open:text-primary">
                                    {String(index + 1).padStart(2, '0')}
                                </span>
                                <span className="flex-1 text-[15px] font-medium sm:text-sm">{faq.question}</span>
                                <span className="grid size-8 shrink-0 place-items-center rounded-full border text-muted-foreground transition-all duration-300 group-hover:border-primary/40 group-hover:text-primary group-open:rotate-45 group-open:border-primary group-open:bg-primary group-open:text-primary-foreground">
                                    <Plus className="size-4"/>
                                </span>
                            </summary>
                            <div className="spesen-antwort px-5 pb-5 text-[15px] leading-relaxed text-muted-foreground sm:pr-14 sm:pl-14 sm:text-sm">
                                {Array.isArray(faq.answer) ? (
                                    <ul className="grid gap-2">
                                        {faq.answer.map((punkt) => (
                                            <li key={punkt} className="relative pl-4 before:absolute before:top-[0.6em] before:left-0 before:size-1.5 before:rounded-full before:bg-primary/60">
                                                {punkt}
                                            </li>
                                        ))}
                                    </ul>
                                ) : (
                                    <p>{faq.answer}</p>
                                )}
                            </div>
                        </details>
                    ))}
                </div>
            </div>
        </section>
    );
}

/** Abschluss, wieder im Nacht-Block wie ganz oben */
function Abschluss({angemeldet, abschlussRef}: {
    angemeldet: boolean;
    abschlussRef: RefObject<HTMLElement | null>;
}) {
    return (
        <section ref={abschlussRef} data-nacht className="spesen-nacht relative isolate overflow-hidden text-white">
            <div aria-hidden className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-flutlicht/50 to-transparent"/>
            <div aria-hidden className="spesen-feld spesen-feld-auslauf pointer-events-none absolute inset-x-0 bottom-0 h-[70%]">
                <div className="absolute inset-0">
                    <Spielfeld className="absolute inset-x-[6%] inset-y-[8%] h-[84%] w-[88%] text-white/15"/>
                </div>
            </div>

            {/* Ringe wie ein Pfiff, der sich ueber den Platz ausbreitet */}
            <div aria-hidden className="pointer-events-none absolute inset-0 grid place-items-center">
                {[0, 2.3, 4.6].map((verzug) => (
                    <div
                        key={verzug}
                        className="spesen-ring absolute size-[34rem] rounded-full border border-flutlicht/20"
                        style={{animationDelay: `${verzug}s`}}
                    />
                ))}
            </div>
            <div aria-hidden className="spesen-koerner pointer-events-none absolute inset-0"/>

            <div data-reveal className="relative mx-auto max-w-2xl px-4 py-20 text-center sm:px-6 sm:py-32">
                <span className="mx-auto mb-6 grid size-14 place-items-center rounded-2xl bg-flutlicht/15 text-flutlicht shadow-[0_0_40px] shadow-flutlicht/20">
                    <Pfeife className="size-7"/>
                </span>
                <h2 className="text-[2rem] leading-tight font-semibold tracking-tight text-balance sm:text-5xl">
                    Bereit für den Abpfiff?
                </h2>
                <p className="mx-auto mt-4 max-w-md text-[15px] leading-relaxed text-white/70 sm:text-base">
                    Registrieren, Zugangsdaten hinterlegen und den ersten Abruf per Knopfdruck starten –
                    danach läuft er jede Nacht von allein.
                </p>
                <Button
                    asChild
                    size="lg"
                    className="mt-8 h-12 w-full bg-flutlicht px-7 text-base text-nacht shadow-lg shadow-flutlicht/25 hover:bg-flutlicht/90 sm:w-auto"
                >
                    <Link to={angemeldet ? '/dashboard' : '/register'}>
                        {angemeldet ? 'Zum Dashboard' : 'Jetzt kostenlos starten'}
                        <ArrowRight className="size-4"/>
                    </Link>
                </Button>
            </div>
        </section>
    );
}

function Fusszeile() {
    return (
        <footer data-nacht className="bg-nacht pt-2 pb-8 text-white sm:pb-10">
            <div className={`${RAHMEN} flex flex-col items-center justify-between gap-5 sm:flex-row`}>
                <div className="flex flex-col items-center gap-1 sm:items-start">
                    <Marke hell/>
                    <span className="text-xs text-white/60">Für Schiedsrichter des Thüringer Fußball-Verbandes</span>
                </div>
                <div className="flex flex-wrap items-center justify-center gap-x-2 text-sm text-white/60">
                    <span className="px-2">© {new Date().getFullYear()} · Jan Vogt</span>
                    <a
                        href="mailto:spesen-generator@jan-vogt.dev"
                        className="inline-flex min-h-11 items-center px-2 transition-colors hover:text-white"
                    >
                        Kontakt
                    </a>
                    <Link to="/datenschutz" className="inline-flex min-h-11 items-center px-2 transition-colors hover:text-white">
                        Datenschutz
                    </Link>
                </div>
            </div>
        </footer>
    );
}

/**
 * Die Anpfiff-Leiste am unteren Rand, nur am Handy. Sie erscheint, sobald
 * die Hauptaktion des Hero aus dem Bild ist, und geht wieder, wenn der
 * Abschluss mit seiner eigenen Aktion auftaucht. Ohne Bewegung erscheint
 * sie ohne Hereingleiten.
 */
function Anpfiffleiste({angemeldet, sichtbar}: { angemeldet: boolean; sichtbar: boolean }) {
    return (
        <div
            inert={!sichtbar}
            className={`fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-[oklch(0.17_0.028_158/0.9)] px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md transition-[translate,opacity] duration-300 ease-out motion-reduce:transition-none sm:hidden ${
                sichtbar ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-full opacity-0'
            }`}
        >
            <Button
                asChild
                size="lg"
                className="h-12 w-full bg-flutlicht text-base text-nacht shadow-lg shadow-flutlicht/20 hover:bg-flutlicht/90"
            >
                <Link to={angemeldet ? '/dashboard' : '/register'}>
                    {angemeldet ? 'Zum Dashboard' : 'Kostenlos starten'}
                    <ArrowRight className="size-4"/>
                </Link>
            </Button>
        </div>
    );
}

/*
 * Die Landingpage bekommt ein paar Eigenheiten am html-Element, solange sie
 * offen ist: 16px Grundschrift auch am Handy (die Anwendung nutzt dort 14px,
 * fuer eine Seite, die einladen soll, ist das zu klein), der Nacht-Ton als
 * Grund hinter der Seite (sonst blitzt beim Ueberscrollen auf iOS Weiss ueber
 * dem dunklen Hero auf) und die passende Farbe fuer die Browserleiste.
 *
 * Dazu viewport-fit=cover: erst damit meldet das iPhone seine sicheren
 * Raender (env(safe-area-inset-*)), und die Anpfiff-Leiste rueckt ueber den
 * Home-Balken. Nur hier, nicht in index.html - die Anwendung rechnet nicht
 * mit diesen Raendern und liefe quer sonst unter die Kamera-Aussparung. Die
 * Landingpage selbst haelt sie ueber .spesen-rahmen frei.
 */
const THEMEFARBE = '#05130b';

function useStartseitenRahmen() {
    useLayoutEffect(() => {
        const wurzel = document.documentElement;
        wurzel.classList.add('spesen-startseite');

        let meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
        const vorher = meta?.content ?? null;
        if (!meta) {
            meta = document.createElement('meta');
            meta.name = 'theme-color';
            document.head.appendChild(meta);
        }
        meta.content = THEMEFARBE;

        const viewport = document.querySelector<HTMLMetaElement>('meta[name="viewport"]');
        const viewportVorher = viewport?.content;
        if (viewport && !viewport.content.includes('viewport-fit')) {
            viewport.content = `${viewport.content}, viewport-fit=cover`;
        }

        return () => {
            wurzel.classList.remove('spesen-startseite');
            if (viewport && viewportVorher !== undefined) {
                viewport.content = viewportVorher;
            }
            if (vorher === null) {
                meta.remove();
            } else {
                meta.content = vorher;
            }
        };
    }, []);
}

export function LandingPage() {
    useStartseitenRahmen();
    useRevealOnScroll();

    const [angemeldet] = useState(isAuthenticated);
    const heroAktion = useRef<HTMLDivElement>(null);
    const abschluss = useRef<HTMLElement>(null);
    const aktionImBild = useImBild(heroAktion);
    const abschlussImBild = useImBild(abschluss, {anfang: false});

    return (
        <div className="spesen-landing flex min-h-screen flex-col bg-background text-foreground">
            <Kopfzeile angemeldet={angemeldet}/>
            <main className="flex-1">
                <Hero angemeldet={angemeldet} ctaRef={heroAktion}/>
                <Aufstellung/>
                <Spielablauf/>
                <Fairplay/>
                <Fragen/>
                <Abschluss angemeldet={angemeldet} abschlussRef={abschluss}/>
            </main>
            <Fusszeile/>
            <Anpfiffleiste angemeldet={angemeldet} sichtbar={!aktionImBild && !abschlussImBild}/>
        </div>
    );
}
