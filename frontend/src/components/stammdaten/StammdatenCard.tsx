import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Separator} from '@/components/ui/separator';
import {BadgeCheck, Contact, ClipboardList, Award} from 'lucide-react';
import type {Stammdaten} from '@/lib/stammdaten';

interface StammdatenCardProps {
    daten: Stammdaten;
}

/** Deutsche Beschriftung je Feld; unbekannte Schlüssel werden aufgehübscht */
const FELD_NAMEN: Record<string, string> = {
    name_vorname: 'Name, Vorname',
    strasse: 'Straße, Nr.',
    plz_ort: 'PLZ, Ort',
    geburtsdatum: 'Geburtsdatum',
    email: 'E-Mail',
    telefon_privat: 'Telefon (privat)',
    telefon_geschaeftlich: 'Telefon (geschäftlich)',
    telefon_mobil: 'Telefon (mobil)',
    ausweisnummer: 'Ausweisnummer',
    ausweisgueltigkeit: 'Ausweisgültigkeit',
    foto_status: 'Foto-Status',
    foto_gueltigkeit: 'Foto-Gültigkeit',
    sr_gebiet: 'SR-Gebiet',
    schiedsrichter_seit: 'Schiedsrichter seit',
    verein: 'Verein',
    fehlmonate: 'Anzahl Fehlmonate',
    zusatzausbildungen: 'Zusatzausbildungen',
    patensystem_am: 'SR Patensystem durchlaufen am',
    kreditor_nr: 'Kreditor Nr',
    debitor_nr: 'Debitor Nr',
    status: 'Status',
    umsatzsteuerpflichtig: 'Umsatzsteuerpflichtig',
    bemerkung: 'Bemerkung',
    qmax_sr: 'QMax-SR',
    qmax_sra1: 'QMax-SRA 1',
    qmax_sra2: 'QMax-SRA 2',
    qmax_beobachter: 'QMax-Beobachter',
};

/**
 * Abschnitte in der Reihenfolge, in der DFBnet sie selbst zeigt.
 *
 * Die Schlüssel stehen bewusst ausgeschrieben da: sie bestimmen Reihenfolge
 * und Gruppierung, die sich aus einem Objekt nicht ablesen lassen.
 */
const ABSCHNITTE: {titel: string; icon: typeof Contact; felder: string[]}[] = [
    {
        titel: 'Persönliche Daten',
        icon: Contact,
        felder: ['name_vorname', 'geburtsdatum', 'strasse', 'plz_ort'],
    },
    {
        titel: 'Kontakt',
        icon: Contact,
        felder: ['email', 'telefon_mobil', 'telefon_privat', 'telefon_geschaeftlich'],
    },
    {
        titel: 'Ausweis',
        icon: BadgeCheck,
        felder: ['ausweisnummer', 'ausweisgueltigkeit', 'foto_status', 'foto_gueltigkeit'],
    },
    {
        titel: 'Meldedaten',
        icon: ClipboardList,
        felder: [
            'sr_gebiet', 'verein', 'schiedsrichter_seit', 'status',
            'zusatzausbildungen', 'fehlmonate', 'patensystem_am',
            'kreditor_nr', 'debitor_nr', 'umsatzsteuerpflichtig', 'bemerkung',
        ],
    },
    {
        titel: 'Qualifikations-Maximum',
        icon: Award,
        felder: ['qmax_sr', 'qmax_sra1', 'qmax_sra2', 'qmax_beobachter'],
    },
];

/** Spalten der Tabelle, die keine Stammdaten sind */
const METAFELDER = ['user_id', 'first_seen_at', 'scraped_at', 'fussball_de_hinweis'];

const sectionHeaderClass = 'flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase';
const fieldRowClass = 'grid grid-cols-[130px_1fr] gap-2 sm:grid-cols-[210px_1fr]';

function formatFieldName(key: string): string {
    return FELD_NAMEN[key] || key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
}

/**
 * Ob ein Wert angezeigt wird.
 *
 * DFBnet schreibt "-" in Felder, die es nicht gibt. Der Scraper übernimmt das
 * im Wortlaut, weil "-" (wirklich leer) und "" (nichts gelesen) beim
 * Speichern auseinandergehalten werden müssen - erst hier fallen beide
 * zusammen und werden weggelassen.
 */
function hatWert(wert: unknown): wert is string {
    return typeof wert === 'string' && wert.trim() !== '' && wert.trim() !== '-';
}

function formatZeitpunkt(iso?: string): string {
    if (!iso) return '';
    try {
        return new Date(iso).toLocaleString('de-DE', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
        }) + ' Uhr';
    } catch {
        return iso;
    }
}

export function StammdatenCard({daten}: StammdatenCardProps) {
    const bekannteFelder = new Set([...ABSCHNITTE.flatMap((a) => a.felder), ...METAFELDER]);

    // Alles, was DFBnet künftig ergänzt, landet hier statt unter den Tisch zu fallen
    const weitereFelder = Object.keys(daten)
        .filter((key) => !bekannteFelder.has(key) && hatWert(daten[key]));

    const abschnitte = [
        ...ABSCHNITTE.map((abschnitt) => ({
            ...abschnitt,
            felder: abschnitt.felder.filter((key) => hatWert(daten[key])),
        })),
        ...(weitereFelder.length > 0
            ? [{titel: 'Weitere Angaben', icon: ClipboardList, felder: weitereFelder}]
            : []),
    ].filter((abschnitt) => abschnitt.felder.length > 0);

    return (
        <Card className="gap-0 overflow-hidden py-0">
            <CardHeader className="flex h-11 flex-row items-center gap-2 px-4 py-0 sm:px-6">
                <BadgeCheck className="size-4 text-muted-foreground"/>
                <CardTitle className="text-sm">Schiedsrichter-Stammdaten</CardTitle>
            </CardHeader>
            <Separator/>
            <CardContent className="space-y-5 p-4 sm:p-6">
                {abschnitte.map((abschnitt) => (
                    <div key={abschnitt.titel} className="space-y-2">
                        <h4 className={sectionHeaderClass}>
                            <abschnitt.icon className="size-3.5"/>
                            {abschnitt.titel}
                        </h4>
                        <div className="grid gap-1.5 rounded-lg border border-dashed p-3 text-sm">
                            {abschnitt.felder.map((key) => (
                                <div key={key} className={fieldRowClass}>
                                    <span className="break-words text-muted-foreground">
                                        {formatFieldName(key)}
                                    </span>
                                    <span className="break-words">{String(daten[key])}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                ))}

                {hatWert(daten.fussball_de_hinweis) && (
                    <p className="text-sm text-muted-foreground">{daten.fussball_de_hinweis}</p>
                )}

                {daten.scraped_at && (
                    <p className="text-xs text-muted-foreground">
                        Zuletzt aus DFBnet abgerufen: {formatZeitpunkt(daten.scraped_at)}
                    </p>
                )}
            </CardContent>
        </Card>
    );
}
