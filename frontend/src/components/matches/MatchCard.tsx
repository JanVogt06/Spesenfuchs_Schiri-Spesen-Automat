import {useState, useEffect, useRef} from 'react';
import type {MatchData, MatchExpenses} from '@/lib/matches';
import {saveMatchExpenses} from '@/lib/matches';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Separator} from '@/components/ui/separator';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {Calendar, ChevronDown, ChevronUp, Download, Users, MapPin, Euro, Car, Check, Loader2, Info} from 'lucide-react';

/** "12,5" oder "12.5" -> 12.5; leer -> null; ungültig -> undefined */
function parseGermanNumber(value: string): number | null | undefined {
    const trimmed = value.trim();
    if (trimmed === '') return null;
    const num = Number(trimmed.replace(',', '.'));
    return Number.isFinite(num) && num >= 0 ? num : undefined;
}

function formatEuro(value: number): string {
    return value.toLocaleString('de-DE', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' €';
}

function toInputValue(value: number | null | undefined): string {
    return value === null || value === undefined ? '' : String(value).replace('.', ',');
}

interface SpesenInfo {
    sr: number | null;
    sra: number | null;
    sr_formatted: string;
    sra_formatted: string;
    is_punktspiel: boolean;
    sra_count?: number;
    hinweis: string | null;
}

interface MatchCardProps {
    match: MatchData & { _spesen?: SpesenInfo };
    index: number;
    filename: string;
    onDownload: (fileFormat: 'docx' | 'pdf') => void;
    downloadingFilename: string | null;
    selected?: boolean;
    onToggleSelected?: () => void;
    /** Wird nach erfolgreichem Speichern aufgerufen, damit die Liste nachzieht */
    onSaved?: () => void;
}

export function MatchCard({
                              match, index, filename, onDownload, downloadingFilename,
                              selected, onToggleSelected, onSaved,
                          }: MatchCardProps) {
    const [isExpanded, setIsExpanded] = useState(false);
    const pdfFilename = filename.replace(/\.docx$/i, '.pdf');

    // Fahrtkosten/ÖVM-Eingaben (als Strings, deutsche Kommaeingabe erlaubt)
    const [expenseInputs, setExpenseInputs] = useState<Record<string, string>>({
        sr_km: toInputValue(match._expenses?.sr_km),
        sr_oevm: toInputValue(match._expenses?.sr_oevm),
        sra1_km: toInputValue(match._expenses?.sra1_km),
        sra1_oevm: toInputValue(match._expenses?.sra1_oevm),
        sra2_km: toInputValue(match._expenses?.sra2_km),
        sra2_oevm: toInputValue(match._expenses?.sra2_oevm),
    });
    const [isSaving, setIsSaving] = useState(false);
    const [saveMessage, setSaveMessage] = useState('');
    const [saveError, setSaveError] = useState('');

    // Sobald der Nutzer etwas tippt, dürfen neu geladene Serverwerte die
    // Eingaben nicht mehr überschreiben
    const hatEigeneEingaben = useRef(false);

    // Wer ist tatsächlich angesetzt? Anzeige und Speichern müssen dieselbe
    // Antwort verwenden, sonst werden Werte gespeichert, für die es kein
    // Eingabefeld gibt.
    const hasSRA1 = !!match.schiedsrichter?.some(sr => sr.rolle === 'SRA 1' && sr.name);
    const hasSRA2 = !!match.schiedsrichter?.some(sr => sr.rolle === 'SRA 2' && sr.name);
    const sichtbareRollen: Record<string, boolean> = {
        sr_km: true, sr_oevm: true,
        sra1_km: hasSRA1, sra1_oevm: hasSRA1,
        sra2_km: hasSRA2, sra2_oevm: hasSRA2,
    };

    // Lädt die Liste neu (z.B. nach einem Scrape oder einer Änderung auf einem
    // anderen Gerät), müssen die Felder nachziehen. Ohne das behielte die Karte
    // ihre Werte vom ersten Rendern und schriebe sie beim nächsten Speichern
    // über den neueren Stand.
    useEffect(() => {
        if (hatEigeneEingaben.current) return;
        setExpenseInputs({
            sr_km: toInputValue(match._expenses?.sr_km),
            sr_oevm: toInputValue(match._expenses?.sr_oevm),
            sra1_km: toInputValue(match._expenses?.sra1_km),
            sra1_oevm: toInputValue(match._expenses?.sra1_oevm),
            sra2_km: toInputValue(match._expenses?.sra2_km),
            sra2_oevm: toInputValue(match._expenses?.sra2_oevm),
        });
    }, [match._expenses]);

    const handleSaveExpenses = async () => {
        if (!match._id) {
            setSaveError('Spieldaten unvollständig, speichern nicht möglich.');
            return;
        }

        // Eingaben parsen und validieren. Für Rollen ohne Eingabefeld wird
        // ausdrücklich null geschickt: ist eine Assistenz nachträglich
        // abgesetzt worden, stünden ihre Kilometer sonst weiter im Dokument,
        // ohne dass es ein Feld gäbe, um sie zu löschen.
        const expenses: MatchExpenses = {};
        for (const key of Object.keys(expenseInputs) as (keyof MatchExpenses)[]) {
            if (!sichtbareRollen[key]) {
                expenses[key] = null;
                continue;
            }
            const parsed = parseGermanNumber(expenseInputs[key]);
            if (parsed === undefined) {
                setSaveError('Bitte nur positive Zahlen eingeben (z.B. 42 oder 7,50).');
                return;
            }
            expenses[key] = parsed;
        }

        setIsSaving(true);
        setSaveError('');
        setSaveMessage('');
        try {
            await saveMatchExpenses(match._id, expenses);
            hatEigeneEingaben.current = false;
            onSaved?.();
            setSaveMessage('Gespeichert – steht beim nächsten Download im Dokument.');
            setTimeout(() => setSaveMessage(''), 4000);
        } catch (err) {
            console.error('Fehler beim Speichern der Fahrtkosten:', err);
            setSaveError('Speichern fehlgeschlagen. Bitte versuche es erneut.');
        } finally {
            setIsSaving(false);
        }
    };

    const getMatchTitle = () => {
        if (match.spiel_info?.heim_team && match.spiel_info?.gast_team) {
            return `${match.spiel_info.heim_team} – ${match.spiel_info.gast_team}`;
        }
        return `Spiel ${index + 1}`;
    };

    const getMatchSubtitle = () => {
        if (match.spiel_info?.anpfiff) {
            try {
                const anpfiff = match.spiel_info.anpfiff;
                let date: Date | null = null;

                // Format: "Samstag · 22.11.2025 · 11:00 Uhr" (DFBnet Format)
                if (anpfiff.includes('·')) {
                    const parts = anpfiff.split('·').map(p => p.trim());
                    // parts[0] = "Samstag", parts[1] = "22.11.2025", parts[2] = "11:00 Uhr"
                    if (parts.length >= 3) {
                        const datePart = parts[1]; // "22.11.2025"
                        const timePart = parts[2].replace('Uhr', '').trim(); // "11:00"
                        const [day, month, year] = datePart.split('.');
                        if (day && month && year) {
                            date = new Date(`${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${timePart}`);
                        }
                    } else if (parts.length === 2) {
                        // Nur Datum ohne Zeit: "Samstag · 22.11.2025"
                        const datePart = parts[1];
                        const [day, month, year] = datePart.split('.');
                        if (day && month && year) {
                            date = new Date(`${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`);
                        }
                    }
                }
                // ISO 8601 Format (z.B. "2025-11-20T15:00:00")
                else if (anpfiff.includes('T') || (anpfiff.includes('-') && !anpfiff.includes('.'))) {
                    date = new Date(anpfiff);
                }
                // Deutsches Format ohne Wochentag (z.B. "20.11.2025 15:00")
                else if (anpfiff.includes('.')) {
                    const parts = anpfiff.split(' ');
                    if (parts.length >= 2) {
                        const [day, month, year] = parts[0].split('.');
                        const time = parts[1].replace('Uhr', '').trim() || '00:00';
                        date = new Date(`${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${time}`);
                    } else {
                        // Nur Datum ohne Uhrzeit
                        const [day, month, year] = parts[0].split('.');
                        date = new Date(`${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`);
                    }
                }
                // Falls bereits ein Timestamp
                else if (!isNaN(Number(anpfiff))) {
                    date = new Date(Number(anpfiff));
                } else {
                    // Fallback: Versuche direktes Parsen
                    date = new Date(anpfiff);
                }

                // Prüfe, ob das Datum gültig ist
                if (!date || isNaN(date.getTime())) {
                    // Kein Fehler loggen, einfach Original zurückgeben
                    return anpfiff;
                }

                return date.toLocaleString('de-DE', {
                    weekday: 'short',
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                }) + ' Uhr';
            } catch {
                // Bei Fehlern einfach den Original-String zurückgeben
                return match.spiel_info.anpfiff;
            }
        }
        return 'Keine Zeitangabe';
    };

    const formatFieldName = (key: string): string => {
        const fieldNames: Record<string, string> = {
            anpfiff: 'Anpfiff',
            heim_team: 'Heim',
            gast_team: 'Gast',
            mannschaftsart: 'Mannschaftsart',
            spielklasse: 'Spielklasse',
            staffel: 'Staffel',
            spieltag: 'Spieltag',
            rolle: 'Rolle',
            name: 'Name',
            telefon: 'Telefon',
            email: 'E-Mail',
            strasse: 'Straße',
            plz_ort: 'PLZ/Ort',
            adresse: 'Adresse',
            platz_typ: 'Platzart',
        };
        return fieldNames[key] || key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
    };

    const sectionHeaderClass = 'flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase';
    const fieldRowClass = 'grid grid-cols-[110px_1fr] gap-2 sm:grid-cols-[130px_1fr]';

    const renderSpielInfo = () => {
        if (!match.spiel_info || Object.keys(match.spiel_info).length === 0) {
            return null;
        }

        // Felder die wir immer anzeigen wollen (auch wenn leer für Konsistenz)
        const priorityFields = ['spielklasse', 'staffel', 'mannschaftsart', 'spieltag'];
        const fieldsToShow = Object.entries(match.spiel_info)
            .filter(([key, value]) =>
                value &&
                !['heim_team', 'gast_team', 'anpfiff'].includes(key) &&
                !key.startsWith('_')
            );

        if (fieldsToShow.length === 0) {
            return null;
        }

        // Sortiere Felder: Prioritäts-Felder zuerst
        fieldsToShow.sort((a, b) => {
            const aIndex = priorityFields.indexOf(a[0]);
            const bIndex = priorityFields.indexOf(b[0]);
            if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex;
            if (aIndex !== -1) return -1;
            if (bIndex !== -1) return 1;
            return 0;
        });

        return (
            <div className="space-y-2">
                <h4 className={sectionHeaderClass}>
                    <Calendar className="size-3.5"/>
                    Spieldetails
                </h4>
                <div className="grid gap-1.5 rounded-lg border border-dashed p-3 text-sm">
                    {fieldsToShow.map(([key, value]) => (
                        <div key={key} className={fieldRowClass}>
                            <span className="break-words text-muted-foreground">{formatFieldName(key)}</span>
                            <span className="break-words">{value}</span>
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    const renderSpesen = () => {
        const spesen = match._spesen;

        if (!spesen) {
            return null;
        }

        // Keine Anzeige wenn keine Spesen berechnet wurden und kein Hinweis vorhanden
        if (!spesen.sr_formatted && !spesen.hinweis) {
            return null;
        }

        // Prüfe ob SRAs angesetzt sind
        const hasSRA = match.schiedsrichter?.some(sr => sr.rolle?.startsWith('SRA'));

        return (
            <div className="space-y-2">
                <h4 className={sectionHeaderClass}>
                    <Euro className="size-3.5"/>
                    Spesen (TFV-Spesenordnung)
                </h4>
                {spesen.sr_formatted ? (
                    <div className="grid gap-1.5 rounded-lg border border-dashed p-3 text-sm">
                        <div className={fieldRowClass}>
                            <span className="text-muted-foreground">SR</span>
                            <span className="font-mono font-medium">{spesen.sr_formatted}</span>
                        </div>
                        {spesen.sra_formatted && hasSRA && (
                            <div className={fieldRowClass}>
                                <span className="text-muted-foreground">SRA</span>
                                <span className="font-mono font-medium">{spesen.sra_formatted}</span>
                            </div>
                        )}
                    </div>
                ) : (
                    spesen.hinweis && (
                        <p className="rounded-lg border border-dashed p-3 text-sm italic text-muted-foreground">
                            {spesen.hinweis}
                        </p>
                    )
                )}
            </div>
        );
    };

    const renderExpenses = () => {
        // Nur Rollen anzeigen, die tatsächlich angesetzt sind (SR immer)
        const rows = [
            {label: 'SR', kmKey: 'sr_km', oevmKey: 'sr_oevm'},
            ...(hasSRA1 ? [{label: 'SRA 1', kmKey: 'sra1_km', oevmKey: 'sra1_oevm'}] : []),
            ...(hasSRA2 ? [{label: 'SRA 2', kmKey: 'sra2_km', oevmKey: 'sra2_oevm'}] : []),
        ];

        // Eine Person gilt als erfasst, sobald km oder ÖVM eingetragen ist (auch 0)
        const erfasstProZeile = rows.map(({kmKey, oevmKey}) =>
            expenseInputs[kmKey].trim() !== '' || expenseInputs[oevmKey].trim() !== ''
        );
        const teilweiseErfasst = erfasstProZeile.some(Boolean) && !erfasstProZeile.every(Boolean);

        return (
            <div className="space-y-2">
                <h4 className={sectionHeaderClass}>
                    <Car className="size-3.5"/>
                    Fahrtkosten & öffentliche VM
                </h4>
                <div className="space-y-3 rounded-lg border border-dashed p-3">
                    <div className="grid grid-cols-[52px_1fr_1fr] gap-2 text-xs text-muted-foreground">
                        <span/>
                        <span>Kilometer</span>
                        <span>Öffentliche VM (€)</span>
                    </div>
                    {rows.map(({label, kmKey, oevmKey}) => {
                        const kmParsed = parseGermanNumber(expenseInputs[kmKey]);
                        const kmCost = typeof kmParsed === 'number' ? kmParsed * 0.3 : null;

                        return (
                            <div key={label} className="grid grid-cols-[52px_1fr_1fr] items-start gap-2">
                                <span className="pt-1.5 text-sm text-muted-foreground">{label}</span>
                                <div>
                                    <Input
                                        value={expenseInputs[kmKey]}
                                        onChange={(e) => { hatEigeneEingaben.current = true; setExpenseInputs(prev => ({...prev, [kmKey]: e.target.value})); }}
                                        placeholder="z.B. 42"
                                        inputMode="decimal"
                                        className="h-8 text-sm"
                                    />
                                    {kmCost !== null && (
                                        <p className="mt-1 font-mono text-xs text-muted-foreground">
                                            = {formatEuro(kmCost)}
                                        </p>
                                    )}
                                </div>
                                <Input
                                    value={expenseInputs[oevmKey]}
                                    onChange={(e) => { hatEigeneEingaben.current = true; setExpenseInputs(prev => ({...prev, [oevmKey]: e.target.value})); }}
                                    placeholder="z.B. 7,50"
                                    inputMode="decimal"
                                    className="h-8 text-sm"
                                />
                            </div>
                        );
                    })}
                    <div className="flex flex-wrap items-center gap-3 pt-1">
                        <Button size="sm" onClick={handleSaveExpenses} disabled={isSaving}>
                            {isSaving ? (
                                <>
                                    <Loader2 className="size-3.5 animate-spin"/>
                                    Speichert...
                                </>
                            ) : (
                                'Speichern'
                            )}
                        </Button>
                        {saveMessage && (
                            <span className="flex items-center gap-1.5 text-xs text-success">
                                <Check className="size-3.5"/>
                                {saveMessage}
                            </span>
                        )}
                        {saveError && (
                            <span className="text-xs text-destructive">{saveError}</span>
                        )}
                    </div>
                    {teilweiseErfasst && (
                        <p className="flex items-start gap-1.5 rounded-lg bg-primary/10 px-3 py-2 text-xs text-primary">
                            <Info className="mt-0.5 size-3.5 shrink-0"/>
                            Die Gesamtsumme im Dokument wird erst berechnet, wenn für jede angesetzte
                            Person etwas eingetragen ist. Trage 0 ein, wenn keine Kosten anfallen.
                        </p>
                    )}
                    <p className="text-xs text-muted-foreground">
                        Kilometer werden mit 0,30 € pro km abgerechnet, die Werte bleiben dauerhaft
                        gespeichert. Für die Gesamtsumme muss bei jeder Person ein Wert stehen
                        (0 eintragen, wenn keine Kosten anfallen).
                    </p>
                </div>
            </div>
        );
    };

    const renderSchiedsrichter = () => {
        if (!match.schiedsrichter || match.schiedsrichter.length === 0) {
            return null;
        }

        return (
            <div className="space-y-2">
                <h4 className={sectionHeaderClass}>
                    <Users className="size-3.5"/>
                    Schiedsrichter
                </h4>
                <div className="space-y-3">
                    {match.schiedsrichter.map((sr, idx) => (
                        <div key={idx} className="grid gap-1.5 rounded-lg border border-dashed p-3 text-sm">
                            {Object.entries(sr)
                                .filter(([_, value]) => value)
                                .map(([key, value]) => (
                                    <div key={key} className={fieldRowClass}>
                                        <span className="break-words text-muted-foreground">{formatFieldName(key)}</span>
                                        <span className="break-words">{value}</span>
                                    </div>
                                ))}
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    const renderSpielstaette = () => {
        if (!match.spielstaette || Object.keys(match.spielstaette).length === 0) {
            return null;
        }

        const fieldsToShow = Object.entries(match.spielstaette).filter(([_, value]) => value);

        if (fieldsToShow.length === 0) {
            return null;
        }

        return (
            <div className="space-y-2">
                <h4 className={sectionHeaderClass}>
                    <MapPin className="size-3.5"/>
                    Spielstätte
                </h4>
                <div className="grid gap-1.5 rounded-lg border border-dashed p-3 text-sm">
                    {fieldsToShow.map(([key, value]) => (
                        <div key={key} className={fieldRowClass}>
                            <span className="break-words text-muted-foreground">{formatFieldName(key)}</span>
                            <span className="break-words">{value}</span>
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    // Kompakte Spesen-Anzeige im Header (nur wenn vorhanden)
    const renderHeaderSpesen = () => {
        const spesen = match._spesen;
        if (!spesen?.sr_formatted) return null;

        // Prüfe ob SRAs angesetzt sind
        const hasSRA = match.schiedsrichter?.some(sr => sr.rolle?.startsWith('SRA'));

        return (
            <span className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                SR {spesen.sr_formatted}
                {spesen.sra_formatted && hasSRA && ` · SRA ${spesen.sra_formatted}`}
            </span>
        );
    };

    return (
        <Card className="gap-0 overflow-hidden py-0 transition-all hover:ring-foreground/20">
            <CardHeader className="px-4 py-3">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 flex-1">
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                            {onToggleSelected && (
                                <input
                                    type="checkbox"
                                    checked={!!selected}
                                    onChange={onToggleSelected}
                                    aria-label={`${getMatchTitle()} für Sammel-Download auswählen`}
                                    className="size-4 shrink-0 accent-foreground"
                                />
                            )}
                            <CardTitle className="break-words text-sm sm:text-base">
                                {getMatchTitle()}
                            </CardTitle>
                            {match._missing_since && (
                                <span
                                    className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive ring-1 ring-destructive/20"
                                    title="Dieses Spiel stand beim letzten Abruf nicht mehr in deiner DFBnet-Ansetzung."
                                >
                                    Nicht mehr angesetzt
                                </span>
                            )}
                            {renderHeaderSpesen()}
                        </div>
                        <p className="flex items-center gap-1.5 break-words text-xs text-muted-foreground sm:text-sm">
                            <Calendar className="size-3.5 shrink-0"/>
                            {getMatchSubtitle()}
                        </p>
                    </div>
                    <div className="flex gap-2 self-start">
                        <Button
                            onClick={() => onDownload('docx')}
                            disabled={downloadingFilename === filename}
                            size="sm"
                            variant="outline"
                            className="whitespace-nowrap"
                        >
                            <Download className="size-3.5"/>
                            {downloadingFilename === filename ? 'Lade...' : 'DOCX'}
                        </Button>
                        <Button
                            onClick={() => onDownload('pdf')}
                            disabled={downloadingFilename === pdfFilename}
                            variant="outline"
                            size="sm"
                            className="whitespace-nowrap"
                        >
                            <Download className="size-3.5"/>
                            {downloadingFilename === pdfFilename ? 'Erstelle...' : 'PDF'}
                        </Button>
                        <Button
                            onClick={() => setIsExpanded(!isExpanded)}
                            variant="ghost"
                            size="icon-sm"
                            aria-label={isExpanded ? 'Details einklappen' : 'Details ausklappen'}
                        >
                            {isExpanded ? (
                                <ChevronUp className="size-4"/>
                            ) : (
                                <ChevronDown className="size-4"/>
                            )}
                        </Button>
                    </div>
                </div>
            </CardHeader>

            {isExpanded && (
                <>
                    <Separator/>
                    <CardContent className="space-y-5 p-4">
                        {renderSpielInfo()}
                        {renderSpesen()}
                        {renderExpenses()}
                        {renderSchiedsrichter()}
                        {renderSpielstaette()}
                    </CardContent>
                </>
            )}
        </Card>
    );
}
