import {type CSSProperties, useEffect, useRef, useState} from 'react';
import {Button} from '@/components/ui/button';
import {useNavigate, Link} from 'react-router-dom';
import {api} from '@/lib/api';
import {magKeineBewegung, useCountUp, useRevealOnScroll, useScrollProgress} from '@/hooks/useReveal';
import {
    FileText,
    Users,
    Shield,
    Zap,
    CheckCircle2,
    ArrowRight,
    Download,
    Receipt,
    MoonStar,
    Plus,
    Calendar,
    Mail,
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

interface Vorteil {
    icon: LucideIcon;
    title: string;
    description: string;
    /** Kachel ueber zwei Spalten, mit waagerechtem Aufbau */
    breit?: boolean;
    /** Die eine dunkle Kachel, die den Nacht-Block von oben aufgreift */
    nacht?: boolean;
}

const FEATURES: Vorteil[] = [
    {
        icon: MoonStar,
        breit: true,
        nacht: true,
        title: 'Läuft, während du schläfst',
        description: 'Jede Nacht um 3 Uhr werden deine Ansetzungen automatisch aus DFBnet geladen und abgerechnet.',
    },
    {
        icon: FileText,
        title: 'Word & PDF',
        description: 'Jede Abrechnung als bearbeitbares DOCX und fertiges PDF, einzeln oder alle als ZIP.',
    },
    {
        icon: Zap,
        title: 'TFV-Spesenordnung eingebaut',
        description: 'Spesensätze für SR und Assistenten werden automatisch nach Spielklasse berechnet.',
    },
    {
        icon: Calendar,
        title: 'Alle Spiele im Blick',
        description: 'Teams, Anstoß, Spielstätte und Schiedsrichter-Team übersichtlich an einem Ort.',
    },
    {
        icon: Shield,
        title: 'Verschlüsselt gespeichert',
        description: 'Deine DFBnet-Zugangsdaten werden mit Fernet-Verschlüsselung gesichert, Passwörter gehasht.',
    },
    {
        icon: Users,
        breit: true,
        title: 'Für jeden Schiedsrichter',
        description: 'Eigener Account und eigene Daten, vom Kreisliga-Neuling bis zum Oberliga-Routinier.',
    },
];

const SCHRITTE = [
    {
        title: 'Registrieren',
        description: 'Account anlegen und DFBnet-Zugangsdaten einmalig hinterlegen.',
    },
    {
        title: 'Anpfiff',
        description: 'Das System liest deine Ansetzungen automatisch aus DFBnet aus, jede Nacht oder auf Knopfdruck.',
    },
    {
        title: 'Abrechnung',
        description: 'Für jedes Spiel entsteht eine fertige Spesenabrechnung mit korrekten Sätzen.',
    },
    {
        title: 'Abpfiff',
        description: 'Word oder PDF herunterladen, unterschreiben, einreichen. Fertig.',
    },
];

const FAQS = [
    {
        question: 'Ist der Service wirklich kostenlos?',
        answer: 'Ja, Spesenfuchs ist zu 100% kostenlos für alle Schiedsrichter in Thüringen. ' +
            'Es gibt keine versteckten Kosten oder Premium-Features.',
    },
    {
        question: 'Wie sicher sind meine DFBnet-Zugangsdaten?',
        answer: 'Deine Zugangsdaten werden mit Fernet-Verschlüsselung (symmetrische Verschlüsselung) sicher gespeichert ' +
            'und sind nur für dich zugänglich. Dein Account-Passwort wird zusätzlich mit PBKDF2-HMAC gehashed. ' +
            'Die Daten werden ausschließlich für die Generierung deiner Spesenberichte verwendet.',
    },
    {
        question: 'Welche Daten werden aus DFBnet ausgelesen?',
        answer: 'Das System liest automatisch alle relevanten Spielinformationen aus: Datum und Uhrzeit, Teams, Spielklasse, ' +
            'Spielort mit Adresse und Platztyp, sowie alle Schiedsrichter-Kontaktdaten (Name, Telefon, E-Mail, Adresse). ' +
            'Diese Daten werden strukturiert in die Dokumente übertragen. Zusätzlich werden deine eigenen Stammdaten ' +
            'aus DFBnet mitgelesen – Anschrift, Ausweis, Verein, Status und dein Qualifikations-Maximum – und im ' +
            'Reiter „Stammdaten" angezeigt. Dein Passfoto wird nicht abgerufen. Außerdem werden deine geleiteten Spiele ' +
            'aller Saisons mit Ergebnis, Kartenstatistik und Gespann geladen, dazu Einsatzbilanz und Lehrabende.',
    },
    {
        question: 'Wie lange dauert die Generierung?',
        answer: 'Ein manueller Abruf dauert je nach Anzahl der Spiele 1-6 Minuten. ' +
            'Da jede Nacht um 3 Uhr automatisch ein Lauf für alle Nutzer startet, sind deine Abrechnungen ' +
            'in der Regel schon fertig, bevor du sie brauchst.',
    },
    {
        question: 'Kann ich die Dokumente nachträglich bearbeiten?',
        answer: 'Ja! Die generierten Word-Dokumente kannst du nach dem Download beliebig mit Microsoft Word oder anderen ' +
            'kompatiblen Programmen bearbeiten und an deine Bedürfnisse anpassen.',
    },
];

/** Inline-Style fuer die gestaffelte Verzoegerung eines [data-reveal]-Elements */
function verzoegerung(millisekunden: number): CSSProperties {
    return {'--reveal-delay': `${millisekunden}ms`} as CSSProperties;
}

/**
 * Spielfeld-Markierungen in Originalmassen (105 x 68 Meter). Die Strichstaerke
 * skaliert bewusst mit: in der gekippten Ebene werden die nahen Linien dadurch
 * breiter als die fernen, so wie auf einem echten Platz.
 */
function Spielfeld({className, proportional}: { className?: string; proportional?: boolean }) {
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
            <circle cx="52.5" cy="34" r="0.5" fill="currentColor" stroke="none"/>
            {/* Strafraum, Torraum, Elfmeterpunkt und Torraumbogen, links */}
            <rect x="0.2" y="13.84" width="16.5" height="40.32"/>
            <rect x="0.2" y="24.84" width="5.5" height="18.32"/>
            <circle cx="11" cy="34" r="0.5" fill="currentColor" stroke="none"/>
            <path d="M16.7 26.69 A 9.15 9.15 0 0 1 16.7 41.31"/>
            {/* dieselben Markierungen gespiegelt, rechts */}
            <rect x="88.3" y="13.84" width="16.5" height="40.32"/>
            <rect x="99.3" y="24.84" width="5.5" height="18.32"/>
            <circle cx="94" cy="34" r="0.5" fill="currentColor" stroke="none"/>
            <path d="M88.3 41.31 A 9.15 9.15 0 0 1 88.3 26.69"/>
            {/* Eckviertel */}
            <path d="M1.2 0.2 A 1 1 0 0 1 0.2 1.2"/>
            <path d="M0.2 66.8 A 1 1 0 0 1 1.2 67.8"/>
            <path d="M103.8 67.8 A 1 1 0 0 1 104.8 66.8"/>
            <path d="M104.8 1.2 A 1 1 0 0 1 103.8 0.2"/>
        </svg>
    );
}

/**
 * Kopfzeile. Sie liegt ueber dem dunklen Hero und ist dort durchsichtig mit
 * hellem Text; erst nach den ersten Pixeln Scrollen legt sie sich auf die
 * Flaeche der Anwendung.
 */
function Kopfzeile() {
    const navigate = useNavigate();
    const [gescrollt, setGescrollt] = useState(false);

    useEffect(() => {
        const pruefen = () => setGescrollt(window.scrollY > 24);
        pruefen();
        window.addEventListener('scroll', pruefen, {passive: true});
        return () => window.removeEventListener('scroll', pruefen);
    }, []);

    return (
        <header
            className={`fixed inset-x-0 top-0 z-50 transition-colors duration-300 ${
                gescrollt ? 'border-b bg-background/80 backdrop-blur-md' : 'border-b border-transparent'
            }`}
        >
            <div className="mx-auto flex h-14 max-w-[96rem] items-center justify-between px-4 sm:px-6">
                <div className="flex items-center gap-2.5">
                    <span
                        className={`grid size-7 place-items-center rounded-lg transition-colors ${
                            gescrollt ? 'bg-primary text-primary-foreground' : 'bg-flutlicht/15 text-flutlicht'
                        }`}
                    >
                        <Receipt className="size-4"/>
                    </span>
                    <span
                        className={`text-sm font-semibold tracking-tight whitespace-nowrap transition-colors ${
                            gescrollt ? 'text-foreground' : 'text-white'
                        }`}
                    >
                        Spesenfuchs
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate('/login')}
                        className={gescrollt ? 'text-muted-foreground' : 'text-white/75 hover:bg-white/10 hover:text-white'}
                    >
                        Anmelden
                    </Button>
                    <Button
                        size="sm"
                        onClick={() => navigate('/register')}
                        className={gescrollt ? '' : 'bg-flutlicht text-nacht hover:bg-flutlicht/90'}
                    >
                        Kostenlos starten
                    </Button>
                </div>
            </div>
        </header>
    );
}

/** Die Beispiel-Abrechnung, die im Hero schwebt */
function Beispielkarte() {
    return (
        <>
            {/* angeschnittene Karte dahinter, damit ein Stapel entsteht */}
            <div className="absolute inset-x-6 -top-5 rotate-[3deg] rounded-xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm">
                <p className="text-sm font-medium text-white/70">SG Blau-Gelb – FC Beispieltal</p>
                <p className="mt-1 text-xs text-white/40">So · 23.11. · 11:00 Uhr</p>
            </div>

            <div className="relative overflow-hidden rounded-xl border border-white/15 bg-[oklch(0.22_0.03_158/0.85)] p-5 shadow-2xl shadow-black/50 backdrop-blur-md">
                {/* Lichtstreifen, als wuerde das Dokument gerade erzeugt */}
                <div
                    aria-hidden
                    className="spesen-scan pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-transparent via-flutlicht/20 to-transparent"
                />

                <div className="relative flex items-start justify-between gap-3">
                    <div>
                        <p className="text-sm font-semibold">SV Grün-Weiß – FC Kreisstadt</p>
                        <p className="mt-1 flex items-center gap-1.5 text-xs text-white/50">
                            <Calendar className="size-3.5"/>
                            Sa · 22.11. · 13:00 Uhr
                        </p>
                    </div>
                    <span className="flex shrink-0 items-center gap-1.5 text-xs text-white/60">
                        <span className="relative grid size-2 place-items-center">
                            <span className="spesen-puls absolute size-2 rounded-full bg-flutlicht"/>
                            <span className="size-2 rounded-full bg-flutlicht"/>
                        </span>
                        Fertig
                    </span>
                </div>

                <div className="relative mt-4 grid gap-1.5 rounded-lg border border-dashed border-white/15 p-3 text-sm">
                    <div className="grid grid-cols-[90px_1fr] gap-2">
                        <span className="text-white/50">SR</span>
                        <span className="font-mono font-medium text-flutlicht">50,00 €</span>
                    </div>
                    <div className="grid grid-cols-[90px_1fr] gap-2">
                        <span className="text-white/50">SRA</span>
                        <span className="font-mono font-medium text-flutlicht">40,00 €</span>
                    </div>
                </div>

                <div className="relative mt-4 flex items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-2.5 py-1 text-xs font-medium text-white/80">
                        <Download className="size-3.5"/>
                        DOCX
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-2.5 py-1 text-xs font-medium text-white/80">
                        <Download className="size-3.5"/>
                        PDF
                    </span>
                    <span className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-flutlicht/15 px-2.5 py-1 text-xs font-medium text-flutlicht">
                        <MoonStar className="size-3.5"/>
                        Heute 03:00
                    </span>
                </div>
            </div>
        </>
    );
}

/** Der dunkle Block ganz oben: Versprechen, Beispiel, Zahlen, Spesensaetze */
function Hero() {
    const navigate = useNavigate();
    const [docCount, setDocCount] = useState<number | null>(null);
    const [zeiger, setZeiger] = useState({x: 0, y: 0});
    const gezaehlt = useCountUp(docCount);

    // Live-Anzahl der erfassten Spiele laden
    useEffect(() => {
        api.get('/api/stats/public')
            .then((response) => setDocCount(response.data.matches_total))
            .catch(() => {
                // Fallback bleibt bei der statischen Anzeige
            });
    }, []);

    // Die Karte dreht sich ein Stueck zum Mauszeiger. Auf Touchgeraeten
    // kommt kein mousemove an, dort bleibt sie schlicht gerade stehen.
    const zeigerBewegt = (ereignis: React.MouseEvent<HTMLElement>) => {
        if (magKeineBewegung()) {
            return;
        }
        const kasten = ereignis.currentTarget.getBoundingClientRect();
        setZeiger({
            x: (ereignis.clientX - kasten.left) / kasten.width - 0.5,
            y: (ereignis.clientY - kasten.top) / kasten.height - 0.5,
        });
    };

    return (
        <section
            className="spesen-nacht relative isolate overflow-hidden text-white"
            onMouseMove={zeigerBewegt}
            onMouseLeave={() => setZeiger({x: 0, y: 0})}
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

            <div className="relative mx-auto grid max-w-[96rem] items-center gap-14 px-4 pt-28 pb-16 sm:px-6 sm:pt-36 lg:grid-cols-[1.05fr_0.95fr] lg:pb-24">
                <div className="text-center lg:text-left">
                    <p
                        className="spesen-aufsteigen mb-5 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-medium text-white/75 backdrop-blur"
                        style={{animationDelay: '60ms'}}
                    >
                        <span className="relative grid size-1.5 place-items-center">
                            <span className="spesen-puls absolute size-1.5 rounded-full bg-flutlicht"/>
                            <span className="size-1.5 rounded-full bg-flutlicht"/>
                        </span>
                        Für Schiedsrichter des Thüringer Fußball-Verbandes
                    </p>

                    <h1 className="text-4xl font-semibold tracking-tight sm:text-6xl lg:text-7xl">
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
                                <span className="text-flutlicht">Papierkram</span>.
                            </span>
                        </span>
                    </h1>

                    <p
                        className="spesen-aufsteigen mx-auto mt-6 max-w-xl text-base text-white/60 sm:text-lg lg:mx-0"
                        style={{animationDelay: '380ms'}}
                    >
                        Deine Spesenabrechnungen entstehen jede Nacht automatisch aus deinen
                        DFBnet-Ansetzungen. Fertig als Word und PDF, bevor du überhaupt daran denkst.
                    </p>

                    <div
                        className="spesen-aufsteigen mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center lg:justify-start"
                        style={{animationDelay: '460ms'}}
                    >
                        <Button
                            size="lg"
                            onClick={() => navigate('/register')}
                            className="w-full bg-flutlicht text-nacht shadow-lg shadow-flutlicht/20 hover:bg-flutlicht/90 sm:w-auto"
                        >
                            Kostenlos starten
                            <ArrowRight className="size-4"/>
                        </Button>
                        <Button
                            size="lg"
                            variant="secondary"
                            onClick={() => navigate('/login')}
                            className="w-full border border-white/20 bg-white/10 text-white hover:bg-white/20 sm:w-auto"
                        >
                            Anmelden
                        </Button>
                    </div>

                    <div
                        className="spesen-aufsteigen mt-8 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-white/55 lg:justify-start"
                        style={{animationDelay: '540ms'}}
                    >
                        {['100% kostenlos', 'Keine Installation', 'Verschlüsselte Daten'].map((eintrag) => (
                            <span key={eintrag} className="flex items-center gap-1.5">
                                <CheckCircle2 className="size-4 text-flutlicht"/>
                                {eintrag}
                            </span>
                        ))}
                    </div>
                </div>

                <div
                    aria-hidden
                    className="spesen-aufsteigen relative mx-auto w-full max-w-sm select-none"
                    style={{animationDelay: '520ms'}}
                >
                    <div className="spesen-schweben relative">
                        <div
                            className="transition-transform duration-300 ease-out"
                            style={{
                                transform: `perspective(1000px) rotateX(${-zeiger.y * 6}deg) rotateY(${zeiger.x * 9}deg)`,
                            }}
                        >
                            <Beispielkarte/>
                        </div>
                    </div>
                </div>
            </div>

            {/* Zahlenband */}
            <div className="relative border-t border-white/10">
                <div className="mx-auto grid max-w-[96rem] divide-y divide-white/10 px-4 sm:grid-cols-3 sm:divide-x sm:divide-y-0 sm:px-6">
                    {[
                        {
                            wert: docCount !== null ? gezaehlt.toLocaleString('de-DE') : '–',
                            label: 'Spiele erfasst',
                        },
                        {wert: '03:00', label: 'Uhr startet der automatische Lauf, jede Nacht'},
                        {wert: '0 €', label: 'Kostenlos für alle SR in Thüringen'},
                    ].map((zahl) => (
                        <div key={zahl.label} className="px-2 py-8 text-center">
                            <p className="font-mono text-3xl font-semibold tracking-tight text-flutlicht sm:text-4xl">
                                {zahl.wert}
                            </p>
                            <p className="mt-1 text-sm text-white/45">{zahl.label}</p>
                        </div>
                    ))}
                </div>
            </div>

            {/* Laufband der Spesensaetze */}
            <div className="relative overflow-hidden border-t border-white/10 py-3">
                <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-nacht to-transparent sm:w-24"/>
                <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-nacht to-transparent sm:w-24"/>
                <div className="spesen-laufband flex w-max">
                    {[0, 1].map((durchlauf) => (
                        <div key={durchlauf} className="flex shrink-0 gap-3 pr-3">
                            <span className="flex items-center rounded-full border border-dashed border-white/15 px-3 py-1 text-xs whitespace-nowrap text-white/40">
                                TFV-Spesenordnung §2, Stand 01.07.2025
                            </span>
                            {SPESENSAETZE.map((satz) => (
                                <span
                                    key={satz.klasse}
                                    className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs whitespace-nowrap text-white/55"
                                >
                                    <span className="font-medium text-white/85">{satz.klasse}</span>
                                    <span className="font-mono text-flutlicht">{satz.sr}</span>
                                    <span className="text-white/25">/</span>
                                    <span className="font-mono">{satz.sra}</span>
                                </span>
                            ))}
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}

/**
 * Uhr auf drei Uhr nachts - die Zeit, zu der der Lauf fuer alle Nutzer
 * startet. Sie steht auf der dunklen Kachel und macht aus der Zusage im
 * Text ein Bild.
 */
function Nachtuhr() {
    return (
        <div className="relative flex shrink-0 flex-col items-center gap-2">
            <svg viewBox="0 0 100 100" className="size-24 sm:size-28" fill="none" aria-hidden>
                <circle cx="50" cy="50" r="46" strokeWidth="1" className="stroke-white/15"/>
                <circle
                    cx="50"
                    cy="50"
                    r="38"
                    strokeWidth="1.5"
                    strokeDasharray="1 7"
                    strokeLinecap="round"
                    className="stroke-flutlicht/40"
                />
                {/* Zeiger auf 03:00 */}
                <line x1="50" y1="50" x2="50" y2="24" strokeWidth="3" strokeLinecap="round" className="stroke-white/70"/>
                <line x1="50" y1="50" x2="74" y2="50" strokeWidth="3" strokeLinecap="round" className="stroke-flutlicht"/>
                <circle cx="50" cy="50" r="3" className="fill-flutlicht stroke-none"/>
            </svg>
            <span className="font-mono text-xs tracking-wide text-white/50">03:00 Uhr</span>
        </div>
    );
}

/** Die dunkle Kachel im hellen Raster, mit Rasen und Uhr */
function NachtKachel({feature}: { feature: Vorteil }) {
    return (
        <div className="spesen-nacht relative isolate flex h-full flex-col justify-between gap-6 overflow-hidden rounded-2xl border border-white/10 p-6 text-white sm:flex-row sm:items-center">
            <div aria-hidden className="spesen-feld pointer-events-none absolute inset-x-0 bottom-0 h-3/4">
                <div className="absolute inset-0">
                    <div className="spesen-rasen absolute inset-0"/>
                </div>
            </div>

            <div className="relative">
                <span className="mb-4 grid size-10 place-items-center rounded-xl bg-flutlicht/15 text-flutlicht">
                    <feature.icon className="size-5"/>
                </span>
                <h3 className="font-medium">{feature.title}</h3>
                <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-white/55">
                    {feature.description}
                </p>
            </div>

            <div className="relative">
                <Nachtuhr/>
            </div>
        </div>
    );
}

/** Eine helle Feature-Kachel, deren Lichtpunkt dem Mauszeiger folgt */
function VorteilKarte({feature}: { feature: Vorteil }) {
    const zeigerBewegt = (ereignis: React.MouseEvent<HTMLDivElement>) => {
        const kasten = ereignis.currentTarget.getBoundingClientRect();
        ereignis.currentTarget.style.setProperty('--mx', `${ereignis.clientX - kasten.left}px`);
        ereignis.currentTarget.style.setProperty('--my', `${ereignis.clientY - kasten.top}px`);
    };

    return (
        <div
            onMouseMove={zeigerBewegt}
            className={`spesen-glanz group relative isolate h-full overflow-hidden rounded-2xl border bg-card p-6 transition duration-300 hover:-translate-y-1 hover:border-primary/30 hover:shadow-xl hover:shadow-primary/5 ${
                // Die breite Kachel stellt Zeichen und Text nebeneinander,
                // sonst bliebe die halbe Flaeche leer.
                feature.breit ? 'sm:flex sm:items-center sm:gap-6' : ''
            }`}
        >
            <span
                className={`relative grid size-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary transition-transform duration-300 group-hover:scale-110 ${
                    feature.breit ? 'mb-4 sm:mb-0 sm:size-14' : 'mb-4'
                }`}
            >
                <feature.icon className={feature.breit ? 'size-5 sm:size-6' : 'size-5'}/>
            </span>
            <div className="relative">
                <h3 className="font-medium">{feature.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                    {feature.description}
                </p>
            </div>
        </div>
    );
}

function Vorteile() {
    return (
        <section className="spesen-band relative isolate overflow-hidden border-b py-20 sm:py-28">
            <div aria-hidden className="spesen-uebergang pointer-events-none absolute inset-x-0 top-0 h-64"/>
            <div className="relative mx-auto max-w-[96rem] px-4 sm:px-6">
                <div data-reveal className="mb-12 max-w-xl">
                    <p className="mb-2 text-xs font-medium tracking-wide text-primary uppercase">Features</p>
                    <h2 className="text-2xl font-semibold tracking-tight text-balance sm:text-4xl">
                        Vom Anstoß bis zur Auszahlung, ohne Umwege
                    </h2>
                </div>

                {/*
                    Zwei Kacheln laufen ueber zwei Spalten. Damit gehen beide
                    Reihen glatt auf - ab sm 2 + 1 + 1 und 1 + 1 + 2, ab lg
                    dieselbe Folge in vier Spalten - und das Raster wirkt
                    gesetzt statt gleichfoermig.
                */}
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    {FEATURES.map((feature, index) => (
                        // Das Einblenden liegt auf dem Rahmen, damit es der
                        // Kachel ihr transform beim Darueberfahren nicht nimmt.
                        <div
                            key={feature.title}
                            data-reveal
                            style={verzoegerung(index * 70)}
                            className={feature.breit ? 'sm:col-span-2' : ''}
                        >
                            {feature.nacht
                                ? <NachtKachel feature={feature}/>
                                : <VorteilKarte feature={feature}/>}
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}

/**
 * Die vier Schritte auf einer Bahn, die beim Scrollen mitlaeuft: untereinander
 * senkrecht, ab lg waagerecht zwischen den Ziffern. Am Kopf der Fuellung
 * laeuft ein Punkt mit, damit zu sehen ist, wo die Bahn gerade steht.
 */
function Spielablauf() {
    const bereich = useRef<HTMLDivElement>(null);
    const fortschritt = useScrollProgress(bereich);
    const stufe = fortschritt * SCHRITTE.length;

    return (
        <section className="relative isolate overflow-hidden py-20 sm:py-28">
            <div aria-hidden className="spesen-punkte pointer-events-none absolute inset-0 opacity-60"/>
            <div className="relative mx-auto max-w-[96rem] px-4 sm:px-6">
                <div data-reveal className="mb-12 max-w-xl">
                    <p className="mb-2 text-xs font-medium tracking-wide text-primary uppercase">Spielablauf</p>
                    <h2 className="text-2xl font-semibold tracking-tight text-balance sm:text-4xl">
                        Von der Registrierung bis zum Abpfiff
                    </h2>
                </div>

                <div ref={bereich} className="relative grid gap-10 lg:grid-cols-4 lg:gap-8">
                    {/* Senkrechte Bahn, solange die Schritte untereinander stehen */}
                    <div
                        aria-hidden
                        className="absolute top-5 bottom-5 left-[1.375rem] w-px bg-border lg:hidden"
                    >
                        <div
                            className="absolute inset-x-0 top-0 bg-primary"
                            style={{height: `${fortschritt * 100}%`}}
                        />
                        {fortschritt > 0 && fortschritt < 1 && (
                            <span
                                className="absolute left-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary ring-4 ring-primary/15"
                                style={{top: `${fortschritt * 100}%`}}
                            />
                        )}
                    </div>

                    {SCHRITTE.map((schritt, index) => {
                        const erreicht = stufe > index + 0.35;
                        const fuellung = Math.min(1, Math.max(0, stufe - (index + 0.5)));

                        return (
                            <div
                                key={schritt.title}
                                data-reveal
                                style={verzoegerung(index * 90)}
                                className="relative pl-16 lg:pl-0"
                            >
                                <div className="absolute top-0 left-0 lg:static lg:mb-4 lg:flex lg:items-center lg:gap-3">
                                    <span
                                        className={`grid size-11 shrink-0 place-items-center rounded-full font-mono text-sm font-semibold transition-all duration-500 ${
                                            erreicht
                                                ? 'bg-primary text-primary-foreground ring-4 ring-primary/15'
                                                : 'bg-muted text-muted-foreground ring-4 ring-transparent'
                                        }`}
                                    >
                                        {String(index + 1).padStart(2, '0')}
                                    </span>
                                    {index < SCHRITTE.length - 1 && (
                                        <span aria-hidden className="relative hidden h-px flex-1 bg-border lg:block">
                                            <span
                                                className="absolute inset-y-0 left-0 bg-primary"
                                                style={{width: `${fuellung * 100}%`}}
                                            />
                                            {fuellung > 0 && fuellung < 1 && (
                                                <span
                                                    className="absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary ring-4 ring-primary/15"
                                                    style={{left: `${fuellung * 100}%`}}
                                                />
                                            )}
                                        </span>
                                    )}
                                </div>
                                <h3 className="font-medium">{schritt.title}</h3>
                                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                                    {schritt.description}
                                </p>
                            </div>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}

function Fragen() {
    return (
        <section className="spesen-band relative isolate overflow-hidden border-y py-20 sm:py-28">
            {/* Spielfeld als Wasserzeichen, sehr blass */}
            <div aria-hidden className="pointer-events-none absolute inset-0">
                <Spielfeld
                    proportional
                    className="absolute top-1/2 left-1/2 w-[115%] max-w-none -translate-x-1/2 -translate-y-1/2 text-foreground/[0.055]"
                />
            </div>

            <div className="relative mx-auto grid max-w-[96rem] gap-10 px-4 sm:px-6 lg:grid-cols-[0.75fr_1.25fr] lg:gap-16">
                <div data-reveal className="lg:sticky lg:top-24 lg:self-start">
                    <p className="mb-2 text-xs font-medium tracking-wide text-primary uppercase">Häufige Fragen</p>
                    <h2 className="text-2xl font-semibold tracking-tight text-balance sm:text-4xl">
                        Fragen & Antworten
                    </h2>
                    <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
                        Etwas offen geblieben? Schreib mir einfach, ich antworte selbst.
                    </p>
                    <a
                        href="mailto:spesen-generator@jan-vogt.dev"
                        className="mt-5 inline-flex items-center gap-2 rounded-xl border bg-card px-4 py-2.5 text-sm font-medium transition-colors hover:border-primary/30 hover:text-primary"
                    >
                        <Mail className="size-4 text-primary"/>
                        spesen-generator@jan-vogt.dev
                    </a>
                </div>

                {/* Eine Liste statt einzelner Karten: die Fragen gehoeren zusammen */}
                <div data-reveal className="divide-y overflow-hidden rounded-2xl border bg-card">
                    {FAQS.map((faq, index) => (
                        <details key={faq.question} className="group">
                            <summary className="flex cursor-pointer list-none items-center gap-4 px-5 py-5 [&::-webkit-details-marker]:hidden">
                                <span className="font-mono text-xs text-muted-foreground transition-colors group-open:text-primary">
                                    {String(index + 1).padStart(2, '0')}
                                </span>
                                <span className="flex-1 text-sm font-medium">{faq.question}</span>
                                <span className="grid size-8 shrink-0 place-items-center rounded-full border text-muted-foreground transition-all duration-300 group-hover:border-primary/40 group-hover:text-primary group-open:rotate-45 group-open:border-primary group-open:bg-primary group-open:text-primary-foreground">
                                    <Plus className="size-4"/>
                                </span>
                            </summary>
                            <p className="spesen-antwort pr-14 pb-5 pl-14 text-sm leading-relaxed text-muted-foreground">
                                {faq.answer}
                            </p>
                        </details>
                    ))}
                </div>
            </div>
        </section>
    );
}

/** Abschluss und Fusszeile, wieder im Nacht-Block wie ganz oben */
function Abschluss() {
    const navigate = useNavigate();

    return (
        <>
            <section className="spesen-nacht relative isolate overflow-hidden text-white">
                <div aria-hidden className="spesen-feld pointer-events-none absolute inset-x-0 bottom-0 h-[70%]">
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

                <div data-reveal className="relative mx-auto max-w-2xl px-4 py-24 text-center sm:px-6 sm:py-32">
                    <h2 className="text-3xl font-semibold tracking-tight text-balance sm:text-5xl">
                        Bereit für den Abpfiff?
                    </h2>
                    <p className="mx-auto mt-4 max-w-md text-sm text-white/60 sm:text-base">
                        Registrieren, Zugangsdaten hinterlegen und ab morgen früh liegen deine
                        Abrechnungen fertig bereit.
                    </p>
                    <Button
                        size="lg"
                        onClick={() => navigate('/register')}
                        className="mt-8 bg-flutlicht text-nacht shadow-lg shadow-flutlicht/20 hover:bg-flutlicht/90"
                    >
                        Jetzt kostenlos starten
                        <ArrowRight className="size-4"/>
                    </Button>
                </div>
            </section>

            <footer className="bg-nacht py-10 text-white">
                <div className="mx-auto max-w-[96rem] px-4 sm:px-6">
                    <div className="flex flex-col items-center justify-between gap-4 border-t border-white/10 pt-8 sm:flex-row">
                        <div className="flex items-center gap-2.5">
                            <span className="grid size-7 place-items-center rounded-lg bg-flutlicht/15 text-flutlicht">
                                <Receipt className="size-4"/>
                            </span>
                            <div className="leading-tight">
                                <span className="block text-sm font-semibold tracking-tight">Spesenfuchs</span>
                                <span className="text-xs text-white/45">
                                    Für Schiedsrichter des Thüringer Fußball-Verbandes
                                </span>
                            </div>
                        </div>
                        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-sm text-white/50">
                            <span>© 2025 · Jan Vogt</span>
                            <a
                                href="mailto:spesen-generator@jan-vogt.dev"
                                className="transition-colors hover:text-white"
                            >
                                Kontakt
                            </a>
                            <Link to="/datenschutz" className="transition-colors hover:text-white">
                                Datenschutz
                            </Link>
                        </div>
                    </div>
                </div>
            </footer>
        </>
    );
}

export function LandingPage() {
    useRevealOnScroll();

    return (
        <div className="flex min-h-screen flex-col bg-background text-foreground">
            <Kopfzeile/>
            <main className="flex-1">
                <Hero/>
                <Vorteile/>
                <Spielablauf/>
                <Fragen/>
            </main>
            <Abschluss/>
        </div>
    );
}
