# Instagram-Beitrag: Vorstellung von Spesenfuchs

Fünf Slides im Format 3:4 (1080 × 1440), in dieser Reihenfolge hochladen:

1. `01-ankuendigung.png` – Abpfiff für den Papierkram
2. `02-problem.png` – Nach dem Spiel ist vor der Abrechnung
3. `03-ablauf.png` – Vier Schritte bis zum Abpfiff
4. `04-funktionen.png` – Mehr als nur Spesen
5. `05-aufruf.png` – Adresse und Link in Bio

Dieselben fünf Slides gibt es als Story in 9:16 (1080 × 1920) unter `story/`.
Oben und unten bleibt dort Platz für die Leisten von Instagram. Auf der letzten
Story ist unter der Adresse eine Lücke frei: Dort den **Link-Sticker** mit
`https://spesenfuchs.jan-vogt.dev` platzieren (Sticker-Symbol → Link).

Die Slides sind keine Grafiken, sondern gebaut aus den Bausteinen der
Landingpage mit deren Beispieldaten: `frontend/src/instagram/Slides.tsx`,
aufrufbar im Dev-Server unter `http://localhost:5173/instagram.html`
(`?s=1` bis `?s=5` für eine einzelne Slide, `&f=story` für die Story). Sie
gehören nicht zum Build.

Neu exportieren, während `npm run dev` in `frontend` läuft:

```bash
marketing/instagram/export.sh
```

## Beschreibung zum Beitrag (Vorschlag)

> Abpfiff für den Papierkram. 🟢
>
> Spesenfuchs erstellt deine Spesenabrechnungen automatisch aus deinen
> DFBnet-Ansetzungen – jede Nacht, mit Satz, Gespann und Spielstätte. Du trägst
> nur noch die Kilometer ein und lädst die Abrechnung als Word oder PDF.
>
> Für Schiedsrichter im Thüringer Fußball-Verband.
> 👉 spesenfuchs.jan-vogt.dev · Link in Bio
>
> #Schiedsrichter #Schiri #TFV #Thüringen #DFBnet #Fußball #Spesen
