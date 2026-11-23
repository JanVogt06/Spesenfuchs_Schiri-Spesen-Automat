import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {apiGet, apiZuruecksetzen} from '@/test/apiMock';
import {downloadAttrappe, type DownloadAttrappe} from '@/test/download';
import {
    downloadDokument,
    EREIGNIS_NAMEN,
    formatEuro,
    getSpielbericht,
    minuteText,
    oeffneDokument,
    spielberichtPfad,
    uhrzeitAus,
    zeitpunktText,
    type SpielberichtDokument,
} from './spielberichte';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

const dokument: SpielberichtDokument = {
    id: 9,
    kategorie: 'Sonderbericht',
    dateiname: 'Sonderbericht.pdf',
    beschreibung: '',
    hochgeladen_von: 'SR',
    hochgeladen_am: '2026-11-22T18:00:00',
    groesse: 1024,
};

let download: DownloadAttrappe;

beforeEach(() => {
    apiZuruecksetzen();
    download = downloadAttrappe();
});

afterEach(() => {
    download.aufraeumen();
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe('spielberichtPfad', () => {
    it('haengt die Herkunft als ?von= an', () => {
        expect(spielberichtPfad(12, 'saison')).toBe('/spielbericht/12?von=saison');
        expect(spielberichtPfad(3, 'spesen')).toBe('/spielbericht/3?von=spesen');
    });
});

describe('formatEuro', () => {
    it('formatiert Betraege deutsch mit Euro-Zeichen', () => {
        // Zwischen Zahl und Zeichen steht ein geschuetztes Leerzeichen
        expect(formatEuro(12.5)).toMatch(/^12,50\s€$/);
        expect(formatEuro(0)).toMatch(/^0,00\s€$/);
        expect(formatEuro(1234.567)).toMatch(/^1\.234,57\s€$/);
    });

    it('zeigt fehlende Werte als Gedankenstrich', () => {
        expect(formatEuro(null)).toBe('–');
        expect(formatEuro(undefined)).toBe('–');
    });
});

describe('uhrzeitAus', () => {
    it('schneidet die Uhrzeit aus einem ISO-Zeitpunkt', () => {
        expect(uhrzeitAus('2026-11-22T13:30:00.000+01:00')).toBe('13:30');
    });

    it.each(['', '2026-11-22', 'Anstoß offen'])('liefert fuer %j einen leeren String', (wert) => {
        expect(uhrzeitAus(wert)).toBe('');
    });

    it('vertraegt null aus alten Datensaetzen', () => {
        expect(uhrzeitAus(null as unknown as string)).toBe('');
    });
});

describe('zeitpunktText', () => {
    it('macht aus einem ISO-Zeitpunkt Datum und Uhrzeit', () => {
        expect(zeitpunktText('2026-11-22T18:00:12.000+01:00')).toBe('22.11.2026, 18:00');
    });

    it('zeigt ein reines Datum ohne Uhrzeit', () => {
        expect(zeitpunktText('2026-11-22')).toBe('22.11.2026');
    });

    it('laesst Unbekanntes unveraendert', () => {
        expect(zeitpunktText('gestern')).toBe('gestern');
        expect(zeitpunktText('')).toBe('');
        expect(zeitpunktText(null as unknown as string)).toBe('');
    });
});

describe('minuteText', () => {
    it('zeigt die Minute mit Hochkomma', () => {
        expect(minuteText({minute: 23, nachspielzeit: null})).toBe("23'");
    });

    it('haengt die Nachspielzeit an', () => {
        expect(minuteText({minute: 90, nachspielzeit: 3})).toBe("90'+3");
    });

    it('laesst eine Nachspielzeit von 0 weg', () => {
        expect(minuteText({minute: 45, nachspielzeit: 0})).toBe("45'");
    });

    it('zeigt die Minute 0', () => {
        expect(minuteText({minute: 0, nachspielzeit: null})).toBe("0'");
    });

    it('liefert ohne Minute einen leeren String', () => {
        expect(minuteText({minute: null, nachspielzeit: 2})).toBe('');
    });
});

describe('EREIGNIS_NAMEN', () => {
    it('kennt jeden Ereignistyp des Spielberichts', () => {
        expect(Object.keys(EREIGNIS_NAMEN).sort()).toEqual([
            'eigentor', 'elfmeterschiessen', 'elfmetertor', 'gelb', 'gelbrot',
            'rot', 'tor', 'unsportlichkeit', 'wechsel', 'zeitstrafe',
        ]);
        expect(EREIGNIS_NAMEN.gelbrot).toBe('Gelb-Rote Karte');
        expect(EREIGNIS_NAMEN.elfmeterschiessen).toBe('Elfmeterschießen');
    });
});

describe('getSpielbericht', () => {
    it('schickt die Herkunft als Parameter mit', async () => {
        apiGet.mockResolvedValue({data: {id: 5}});

        await expect(getSpielbericht(5, 'saison')).resolves.toEqual({id: 5});

        expect(apiGet).toHaveBeenCalledWith('/api/spielberichte/5', {params: {quelle: 'saison'}});
    });

    it.each([undefined, null, ''])('laesst die Parameter ohne Herkunft (%j) weg', async (quelle) => {
        apiGet.mockResolvedValue({data: {id: 5}});

        await getSpielbericht(5, quelle);

        expect(apiGet).toHaveBeenCalledWith('/api/spielberichte/5', {params: undefined});
    });
});

describe('downloadDokument', () => {
    it('laedt das Dokument als Blob und speichert es unter seinem Dateinamen', async () => {
        const blob = new Blob(['pdf']);
        apiGet.mockResolvedValue({data: blob});

        await downloadDokument(4, dokument);

        expect(apiGet).toHaveBeenCalledWith('/api/spielberichte/4/dokumente/9', {
            responseType: 'blob',
            params: {aktion: 'laden'},
        });
        expect(download.createObjectURL).toHaveBeenCalledWith(blob);
        expect(download.klicks).toEqual([{href: 'blob:test/1', download: 'Sonderbericht.pdf', imDokument: true}]);
    });
});

describe('oeffneDokument', () => {
    function fensterAttrappe() {
        return {location: {href: ''}, close: vi.fn()};
    }

    it('oeffnet das Fenster sofort und leitet es danach auf das PDF', async () => {
        vi.useFakeTimers();
        const fenster = fensterAttrappe();
        const open = vi.fn(() => fenster);
        vi.stubGlobal('open', open);
        let aufloesen: (wert: {data: Blob}) => void = () => {};
        apiGet.mockReturnValue(new Promise((resolve) => {
            aufloesen = resolve;
        }));

        const laeuft = oeffneDokument(4, dokument);
        // Noch vor der Antwort - sonst blockt Safari das Pop-up
        expect(open).toHaveBeenCalledWith('', '_blank');

        aufloesen({data: new Blob(['pdf'])});
        await laeuft;

        expect(apiGet).toHaveBeenCalledWith('/api/spielberichte/4/dokumente/9', {
            responseType: 'blob',
            params: {aktion: 'oeffnen'},
        });
        expect(fenster.location.href).toBe('blob:test/1');
        expect(download.klicks).toHaveLength(0);

        // Die URL bleibt eine Minute gueltig
        vi.advanceTimersByTime(59_999);
        expect(download.revokeObjectURL).not.toHaveBeenCalled();
        vi.advanceTimersByTime(1);
        expect(download.revokeObjectURL).toHaveBeenCalledWith('blob:test/1');
    });

    it('laedt herunter, wenn der Browser das Fenster blockt', async () => {
        vi.stubGlobal('open', vi.fn(() => null));
        apiGet.mockResolvedValue({data: new Blob(['pdf'])});

        await oeffneDokument(4, dokument);

        expect(download.klicks).toHaveLength(1);
        expect(download.klicks[0].download).toBe('Sonderbericht.pdf');
    });

    it('schliesst das leere Fenster wieder, wenn das Laden scheitert', async () => {
        const fenster = fensterAttrappe();
        vi.stubGlobal('open', vi.fn(() => fenster));
        apiGet.mockRejectedValue(new Error('Keine Verbindung'));

        await expect(oeffneDokument(4, dokument)).rejects.toThrow('Keine Verbindung');

        expect(fenster.close).toHaveBeenCalled();
        expect(download.createObjectURL).not.toHaveBeenCalled();
    });
});
