import {vi} from 'vitest';

export interface DownloadAttrappe {
    createObjectURL: ReturnType<typeof vi.fn<(blob: Blob) => string>>;
    revokeObjectURL: ReturnType<typeof vi.fn<(url: string) => void>>;
    /** Die angeklickten Links, mit Zustand zum Zeitpunkt des Klicks */
    klicks: {href: string; download: string | null; imDokument: boolean}[];
    aufraeumen: () => void;
}

/**
 * jsdom kennt weder URL.createObjectURL noch Downloads. Ersetzt beides und
 * merkt sich, welche Links geklickt wurden, statt zu navigieren.
 */
export function downloadAttrappe(): DownloadAttrappe {
    let zaehler = 0;
    const createObjectURL = vi.fn<(blob: Blob) => string>(() => `blob:test/${++zaehler}`);
    const revokeObjectURL = vi.fn<(url: string) => void>();
    const klicks: DownloadAttrappe['klicks'] = [];

    const ziel = window.URL as unknown as Record<string, unknown>;
    const vorher = {create: ziel.createObjectURL, revoke: ziel.revokeObjectURL};
    Object.defineProperty(ziel, 'createObjectURL', {configurable: true, writable: true, value: createObjectURL});
    Object.defineProperty(ziel, 'revokeObjectURL', {configurable: true, writable: true, value: revokeObjectURL});

    const klick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
        klicks.push({
            href: this.getAttribute('href') ?? '',
            download: this.getAttribute('download'),
            imDokument: document.body.contains(this),
        });
    });

    return {
        createObjectURL,
        revokeObjectURL,
        klicks,
        aufraeumen: () => {
            klick.mockRestore();
            Object.defineProperty(ziel, 'createObjectURL', {configurable: true, writable: true, value: vorher.create});
            Object.defineProperty(ziel, 'revokeObjectURL', {configurable: true, writable: true, value: vorher.revoke});
        },
    };
}
