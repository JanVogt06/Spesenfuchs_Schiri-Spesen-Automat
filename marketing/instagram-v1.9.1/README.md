# Instagram post: introducing Spesenfuchs

Made at version v1.9.1 (shows the app as of that release).

Five slides in 3:4 format (1080 × 1440), to be uploaded in this order:

1. `01-ankuendigung.png` – Final whistle for the paperwork (announcement)
2. `02-problem.png` – After the match is before the expense claim (the problem)
3. `03-ablauf.png` – Four steps to the final whistle (how it works)
4. `04-funktionen.png` – More than just expenses (features)
5. `05-aufruf.png` – Address and link in bio (call to action)

The same five slides exist as a story in 9:16 (1080 × 1920) under `story/`.
Space is left at the top and bottom for Instagram's bars. On the last story,
a gap is left free below the address: place the **link sticker** with
`https://spesenfuchs.jan-vogt.dev` there (sticker icon → Link).

The slides are not graphics but are built from the building blocks of the
landing page with its sample data: `frontend/src/instagram/Slides.tsx`,
available in the dev server at `http://localhost:5173/instagram.html`
(`?s=1` to `?s=5` for a single slide, `&f=story` for the story). They are
not part of the build.

To export again while `npm run dev` is running in `frontend`:

```bash
marketing/instagram-v1.9.1/export.sh
```

## Post caption (suggestion)

The caption is deliberately kept in German: it is the public text for German
referees in the Thuringian football association (TFV).

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
