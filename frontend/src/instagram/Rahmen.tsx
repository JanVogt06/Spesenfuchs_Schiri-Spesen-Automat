import type {ReactNode} from 'react';
import {ArrowRight, Link2, Route} from 'lucide-react';
import {Marke, Spielfeld} from '@/pages/Landing';

/*
 * Gemeinsamer Rahmen aller Instagram-Beitraege: Nacht-Grund, Flutlicht, Korn,
 * Marke oben, Fortschritt unten. Format 3:4 (540 x 720), mit ?f=story 9:16
 * (540 x 960) - dort bleibt oben und unten Platz fuer die Leisten von
 * Instagram, Wisch-Hinweis und Punkte entfallen.
 */

export const ADRESSE = 'spesenfuchs.jan-vogt.dev';
export const STORY = new URLSearchParams(window.location.search).get('f') === 'story';

function Fortschritt({nummer, anzahl}: { nummer: number; anzahl: number }) {
    return (
        <span className="flex items-center gap-1.5">
            {Array.from({length: anzahl}, (_, index) => (
                <span
                    key={index}
                    className={`h-1.5 rounded-full ${index + 1 === nummer ? 'w-6 bg-flutlicht' : 'w-1.5 bg-white/25'}`}
                />
            ))}
        </span>
    );
}

export function Folie({nummer, anzahl, feld, children}: {
    nummer: number;
    anzahl: number;
    feld?: boolean;
    children: ReactNode;
}) {
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
                <span className="text-[13px] font-medium text-white/45 tabular-nums">{nummer} / {anzahl}</span>
            </header>

            <div className={`relative flex min-h-0 flex-1 flex-col px-10 pt-7 ${STORY ? 'justify-center pb-[130px]' : ''}`}>
                {children}
            </div>

            {!STORY && <footer className="relative flex items-center justify-between px-10 pt-5 pb-9">
                <Fortschritt nummer={nummer} anzahl={anzahl}/>
                {nummer < anzahl ? (
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

export function Etikett({children}: { children: ReactNode }) {
    return (
        <p className="inline-flex w-fit items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[13px] font-medium text-white/80">
            <span className="size-1.5 rounded-full bg-flutlicht"/>
            {children}
        </p>
    );
}

export function Titel({children}: { children: ReactNode }) {
    return (
        <h2 className="mt-4 text-[40px] leading-[1.05] font-semibold tracking-[-0.03em] text-balance">{children}</h2>
    );
}

export function Leucht({children}: { children: ReactNode }) {
    return <span className="spesen-leuchtschrift text-flutlicht">{children}</span>;
}

export function Kachel({icon: Icon, titel, text, children}: {
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

/** Alle Slides untereinander, mit ?s=n nur die n-te - fuer den Export */
export function Beitrag({folien}: { folien: (() => ReactNode)[] }) {
    const gewaehlt = Number(new URLSearchParams(window.location.search).get('s'));
    const auswahl = gewaehlt >= 1 && gewaehlt <= folien.length ? [folien[gewaehlt - 1]] : folien;

    return (
        <div className={gewaehlt ? '' : 'grid justify-center gap-6 bg-neutral-900 p-6'}>
            {auswahl.map((Inhalt, index) => <Inhalt key={index}/>)}
        </div>
    );
}
