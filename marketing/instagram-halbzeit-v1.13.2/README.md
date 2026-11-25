# Instagram post: half-time update

Made at version v1.13.2 (shows the app as of that release).

Covers everything since the last post: the update story of November (made at
v1.10.1) gets a recap slide, followed by what came after it. Eight slides in
3:4 format (1080 × 1440), to be uploaded in this order:

1. `01-halbzeit.png` – Half-time, time to take stock (hook)
2. `02-november.png` – Recap of the November story: observations, app,
   made for the phone
3. `03-spiele.png` – All matches, one list (*Spiele* tab: upcoming/past,
   search, months, *Aktualisieren*, new tab bar)
4. `04-fahrten.png` – Who drives with whom (mileage suggestions, carpools,
   meeting points)
5. `05-statistik.png` – What the season brings in (*Statistik* tab with
   estimated travel costs and the venue map)
6. `06-spielberichte.png` – The match report right at the match
7. `07-ausserdem.png` – More under the hood (NOFV form, Spielkennung on the
   claim, whole season from DFBnet, login lock)
8. `08-aufruf.png` – Just reload (call to action)

The same eight slides exist as a story in 9:16 (1080 × 1920) under `story/`.
Space is left at the top and bottom for Instagram's bars. On the last story,
a gap is left free below the address: place the **link sticker** with
`https://spesenfuchs.jan-vogt.dev` there (sticker icon → Link).

Like the earlier posts, it is built from recreated excerpts with made-up data:
`frontend/src/instagram/Halbzeit.tsx`, in the dev server at
`http://localhost:5173/instagram-halbzeit.html` (`?s=1` to `?s=8` for a single
slide, `&f=story` for the story). The frame is shared with the other posts
(`Rahmen.tsx`).

To export again while `npm run dev` is running in `frontend`:

```bash
marketing/instagram-halbzeit-v1.13.2/export.sh
```

## Post caption (suggestion)

The caption is deliberately kept in German: it is the public text for German
referees in the Thuringian football association (TFV).

> Halbzeit – Zeit für Bilanz. 🟢
>
> Seit dem letzten Beitrag ist bei Spesenfuchs einiges dazugekommen:
> 📊 Statistik: Spesen und Fahrtkosten deiner Saison, mit Karte aller Spielstätten
> 🚗 Kilometer-Vorschläge fürs ganze Gespann – mit Fahrgemeinschaft oder Treffpunkt
> 📋 Spielberichte aus DFBnet direkt am Spiel
> 📅 Alle Spiele in einer Liste, kommend und vergangen, durchsuchbar
> Dazu aus dem November: deine Beobachtungen, Spesenfuchs als App und viel Feinschliff fürs Handy.
>
> Schon live – einfach neu laden.
> 👉 spesenfuchs.jan-vogt.dev · Link in Bio
>
> #Schiedsrichter #Schiri #TFV #Thüringen #DFBnet #Fußball #Spesen
