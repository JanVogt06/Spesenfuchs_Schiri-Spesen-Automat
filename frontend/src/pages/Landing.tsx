import {useState, useEffect} from 'react';
import {Button} from '@/components/ui/button';
import {useNavigate, Link} from 'react-router-dom';
import {api} from '@/lib/api';
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
    ChevronDown,
    Calendar,
} from 'lucide-react';

export function LandingPage() {
    const navigate = useNavigate();
    const [docCount, setDocCount] = useState<number | null>(null);

    // Live-Anzahl der generierten Dokumente laden
    useEffect(() => {
        api.get('/api/stats/public')
            .then((response) => setDocCount(response.data.matches_total))
            .catch(() => {
                // Fallback bleibt bei statischer Anzeige
            });
    }, []);

    const stats = [
        {
            value: docCount !== null ? docCount.toLocaleString('de-DE') : '400+',
            label: 'Spiele erfasst',
        },
        {value: '03:00', label: 'Uhr startet der automatische Lauf, jede Nacht'},
        {value: '0 €', label: 'Kostenlos für alle SR in Thüringen'},
    ];

    const features = [
        {
            icon: MoonStar,
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
            title: 'Für jeden Schiedsrichter',
            description: 'Eigener Account und eigene Daten, vom Kreisliga-Neuling bis zum Oberliga-Routinier.',
        }
    ];

    const steps = [
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
        }
    ];

    const faqs = [
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
                'Reiter „Stammdaten" angezeigt. Dein Passfoto wird nicht abgerufen.',
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

    return (
        <div className="flex min-h-screen flex-col bg-background text-foreground">
            {/* Header */}
            <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-sm">
                <div className="mx-auto flex h-14 max-w-[96rem] items-center justify-between px-4 sm:px-6">
                    <div className="flex items-center gap-2.5">
                        <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground">
                            <Receipt className="size-4"/>
                        </span>
                        <span className="text-sm font-semibold tracking-tight whitespace-nowrap">Spesenfuchs</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => navigate('/login')}
                            className="text-muted-foreground"
                        >
                            Anmelden
                        </Button>
                        <Button size="sm" onClick={() => navigate('/register')}>
                            Kostenlos starten
                        </Button>
                    </div>
                </div>
            </header>

            <main className="flex-1">
                {/* Hero */}
                <section className="relative overflow-hidden">
                    {/* Querliegendes Spielfeld als Hintergrund-Grafik */}
                    <div aria-hidden className="pointer-events-none absolute inset-0">
                        {/* Außenlinie */}
                        <div className="absolute top-1/2 left-1/2 aspect-[105/68] w-[min(92%,52rem)] -translate-x-1/2 -translate-y-1/2 rounded-sm border border-primary/15">
                            {/* Mittellinie */}
                            <div className="absolute top-0 left-1/2 h-full w-px -translate-x-1/2 bg-primary/15"/>
                            {/* Mittelkreis + Anstoßpunkt */}
                            <div className="absolute top-1/2 left-1/2 aspect-square w-[26%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/15"/>
                            <div className="absolute top-1/2 left-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/25"/>
                            {/* Strafraum + Torraum links */}
                            <div className="absolute top-1/2 left-0 h-[55%] w-[16%] -translate-y-1/2 border border-l-0 border-primary/15"/>
                            <div className="absolute top-1/2 left-0 h-[26%] w-[6%] -translate-y-1/2 border border-l-0 border-primary/15"/>
                            {/* Strafraum + Torraum rechts */}
                            <div className="absolute top-1/2 right-0 h-[55%] w-[16%] -translate-y-1/2 border border-r-0 border-primary/15"/>
                            <div className="absolute top-1/2 right-0 h-[26%] w-[6%] -translate-y-1/2 border border-r-0 border-primary/15"/>
                            {/* Elfmeterpunkte */}
                            <div className="absolute top-1/2 left-[11%] size-1 -translate-y-1/2 rounded-full bg-primary/20"/>
                            <div className="absolute top-1/2 right-[11%] size-1 -translate-y-1/2 rounded-full bg-primary/20"/>
                        </div>
                    </div>

                    <div className="relative mx-auto grid max-w-[96rem] gap-14 px-4 py-20 sm:px-6 sm:py-28 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
                        <div className="text-center lg:text-left">
                            <p className="mb-4 inline-flex items-center gap-1.5 rounded-full border border-dashed border-primary/40 px-3 py-1 text-xs font-medium text-primary">
                                <Zap className="size-3.5"/>
                                Für Schiedsrichter des Thüringer Fußball-Verbandes
                            </p>
                            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-6xl">
                                Abpfiff für den{' '}
                                <span className="text-primary">Papierkram</span>.
                            </h1>
                            <p className="mx-auto mt-5 max-w-xl text-base text-muted-foreground sm:text-lg lg:mx-0">
                                Deine Spesenabrechnungen entstehen jede Nacht automatisch aus deinen
                                DFBnet-Ansetzungen. Fertig als Word und PDF, bevor du überhaupt daran denkst.
                            </p>

                            <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center lg:justify-start">
                                <Button size="lg" onClick={() => navigate('/register')} className="w-full sm:w-auto">
                                    Kostenlos starten
                                    <ArrowRight className="size-4"/>
                                </Button>
                                <Button
                                    size="lg"
                                    variant="outline"
                                    onClick={() => navigate('/login')}
                                    className="w-full sm:w-auto"
                                >
                                    Anmelden
                                </Button>
                            </div>

                            <div className="mt-8 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-muted-foreground lg:justify-start">
                                {['100% kostenlos', 'Keine Installation', 'Verschlüsselte Daten'].map((item) => (
                                    <span key={item} className="flex items-center gap-1.5">
                                        <CheckCircle2 className="size-4 text-primary"/>
                                        {item}
                                    </span>
                                ))}
                            </div>
                        </div>

                        {/* Produkt-Mockup: generierte Abrechnung */}
                        <div aria-hidden className="relative mx-auto w-full max-w-sm select-none">
                            {/* Karte im Hintergrund */}
                            <div className="absolute inset-x-4 -top-4 rotate-2 rounded-xl bg-card p-4 opacity-60 ring-1 ring-foreground/10">
                                <div className="flex items-center justify-between">
                                    <span className="text-sm font-medium">SG Blau-Gelb – FC Beispieltal</span>
                                </div>
                                <p className="mt-1 text-xs text-muted-foreground">So · 23.11. · 11:00 Uhr</p>
                            </div>

                            {/* Karte im Vordergrund */}
                            <div className="relative -rotate-1 rounded-xl bg-card p-5 ring-1 ring-foreground/10">
                                <div className="flex items-start justify-between gap-3">
                                    <div>
                                        <p className="text-sm font-semibold">SV Grün-Weiß – FC Kreisstadt</p>
                                        <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                                            <Calendar className="size-3.5"/>
                                            Sa · 22.11. · 13:00 Uhr
                                        </p>
                                    </div>
                                    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                                        <span className="size-2 rounded-full bg-success"/>
                                        Fertig
                                    </span>
                                </div>

                                <div className="mt-4 grid gap-1.5 rounded-lg border border-dashed p-3 text-sm">
                                    <div className="grid grid-cols-[90px_1fr] gap-2">
                                        <span className="text-muted-foreground">SR</span>
                                        <span className="font-mono font-medium">50,00 €</span>
                                    </div>
                                    <div className="grid grid-cols-[90px_1fr] gap-2">
                                        <span className="text-muted-foreground">SRA</span>
                                        <span className="font-mono font-medium">40,00 €</span>
                                    </div>
                                </div>

                                <div className="mt-4 flex gap-2">
                                    <span className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium">
                                        <Download className="size-3.5"/>
                                        DOCX
                                    </span>
                                    <span className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium">
                                        <Download className="size-3.5"/>
                                        PDF
                                    </span>
                                    <span className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                                        <MoonStar className="size-3.5"/>
                                        Heute 03:00
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Stat-Band */}
                <section className="border-y bg-card">
                    <div className="mx-auto grid max-w-[96rem] gap-8 px-4 py-10 sm:grid-cols-3 sm:px-6">
                        {stats.map((stat) => (
                            <div key={stat.label} className="text-center">
                                <p className="font-mono text-3xl font-semibold tracking-tight text-primary sm:text-4xl">
                                    {stat.value}
                                </p>
                                <p className="mt-1 text-sm text-muted-foreground">{stat.label}</p>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Features */}
                <section className="mx-auto max-w-[96rem] px-4 py-20 sm:px-6">
                    <div className="mb-12 max-w-xl">
                        <p className="mb-2 text-xs font-medium tracking-wide text-primary uppercase">
                            Features
                        </p>
                        <h2 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
                            Vom Anstoß bis zur Auszahlung, ohne Umwege
                        </h2>
                    </div>

                    <div className="grid gap-px overflow-hidden rounded-xl bg-border ring-1 ring-foreground/10 sm:grid-cols-2 lg:grid-cols-3">
                        {features.map((feature, index) => (
                            <div key={index} className="bg-card p-6 transition-colors hover:bg-muted/50">
                                <span className="mb-4 grid size-9 place-items-center rounded-lg bg-primary/10">
                                    <feature.icon className="size-4.5 text-primary"/>
                                </span>
                                <h3 className="font-medium">{feature.title}</h3>
                                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                                    {feature.description}
                                </p>
                            </div>
                        ))}
                    </div>
                </section>

                {/* So läuft's ab */}
                <section className="mx-auto max-w-[96rem] px-4 py-20 sm:px-6">
                    <div className="mb-12 max-w-xl">
                        <p className="mb-2 text-xs font-medium tracking-wide text-primary uppercase">
                            Spielablauf
                        </p>
                        <h2 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
                            Von der Registrierung bis zum Abpfiff
                        </h2>
                    </div>

                    <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
                        {steps.map((step, index) => (
                            <div key={index} className="relative">
                                <div className="mb-3 flex items-center gap-3">
                                    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary font-mono text-sm font-semibold text-primary-foreground">
                                        {index + 1}
                                    </span>
                                    {index < steps.length - 1 && (
                                        <span aria-hidden className="hidden h-px flex-1 border-t border-dashed lg:block"/>
                                    )}
                                </div>
                                <h3 className="font-medium">{step.title}</h3>
                                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                                    {step.description}
                                </p>
                            </div>
                        ))}
                    </div>
                </section>

                {/* FAQ */}
                <section className="mx-auto max-w-2xl px-4 py-20 sm:px-6">
                    <div className="mb-10 text-center">
                        <p className="mb-2 text-xs font-medium tracking-wide text-primary uppercase">
                            Häufige Fragen
                        </p>
                        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                            Fragen & Antworten
                        </h2>
                    </div>

                    <div className="space-y-2">
                        {faqs.map((faq, index) => (
                            <details
                                key={index}
                                className="group rounded-xl bg-card ring-1 ring-foreground/10 open:ring-primary/30"
                            >
                                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-sm font-medium [&::-webkit-details-marker]:hidden">
                                    {faq.question}
                                    <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"/>
                                </summary>
                                <p className="px-5 pb-4 text-sm leading-relaxed text-muted-foreground">
                                    {faq.answer}
                                </p>
                            </details>
                        ))}
                    </div>
                </section>

                {/* Abschluss-CTA */}
                <section className="mx-auto max-w-[96rem] px-4 pb-20 sm:px-6">
                    <div className="relative overflow-hidden rounded-2xl bg-primary px-6 py-14 text-center text-primary-foreground sm:py-16">
                        {/* Mittelkreis-Motiv */}
                        <div aria-hidden className="pointer-events-none absolute inset-0">
                            <div className="absolute top-1/2 left-1/2 size-[28rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary-foreground/15"/>
                            <div className="absolute top-1/2 left-0 h-px w-full bg-primary-foreground/10"/>
                        </div>
                        <div className="relative">
                            <h2 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
                                Bereit für den Abpfiff?
                            </h2>
                            <p className="mx-auto mt-2 max-w-md text-sm text-primary-foreground/80 sm:text-base">
                                Registrieren, Zugangsdaten hinterlegen und ab morgen früh liegen deine
                                Abrechnungen fertig bereit.
                            </p>
                            <Button
                                size="lg"
                                variant="secondary"
                                onClick={() => navigate('/register')}
                                className="mt-6"
                            >
                                Jetzt kostenlos starten
                                <ArrowRight className="size-4"/>
                            </Button>
                        </div>
                    </div>
                </section>
            </main>

            {/* Footer */}
            <footer className="border-t py-10">
                <div className="mx-auto max-w-[96rem] px-4 sm:px-6">
                    <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
                        <div className="flex items-center gap-2.5">
                            <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground">
                                <Receipt className="size-4"/>
                            </span>
                            <div className="leading-tight">
                                <span className="block text-sm font-semibold tracking-tight">Spesenfuchs</span>
                                <span className="text-xs text-muted-foreground">
                                    Für Schiedsrichter des Thüringer Fußball-Verbandes
                                </span>
                            </div>
                        </div>
                        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                            <span>© 2025 · Jan Vogt</span>
                            <a
                                href="mailto:spesen-generator@jan-vogt.dev"
                                className="transition-colors hover:text-foreground"
                            >
                                Kontakt
                            </a>
                            <Link to="/datenschutz" className="transition-colors hover:text-foreground">
                                Datenschutz
                            </Link>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    );
}
