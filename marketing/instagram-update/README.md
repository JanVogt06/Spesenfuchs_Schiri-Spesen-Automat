# Instagram-Story: Update seit der Vorstellung

Fünf Story-Slides im Format 9:16 (1080 × 1920) zu allem, was seit dem
Vorstellungsbeitrag im September dazugekommen ist. In dieser Reihenfolge als
Story hochladen:

1. `01-update.png` – Nachspielzeit mit Neuem
2. `02-beobachtungen.png` – Deine Noten auf einen Blick (Reiter *Beobachtungen*)
3. `03-app.png` – Ab auf den Homescreen (installierbar, Tab-Leiste)
4. `04-feinschliff.png` – Am Handy jetzt ein Heimspiel (Kontakte antippen,
   größere Felder, Kennzahlen nebeneinander, Meldung ohne Netz)
5. `05-aufruf.png` – Einfach neu laden

Oben und unten bleibt Platz für die Leisten von Instagram. Auf der letzten
Slide ist unter der Adresse eine Lücke frei: Dort den **Link-Sticker** mit
`https://spesenfuchs.jan-vogt.dev` platzieren (Sticker-Symbol → Link). Damit
die Story nach 24 Stunden nicht weg ist, kann sie als Highlight („Updates“) im
Profil bleiben.

Gebaut ist sie wie der erste Beitrag aus nachgebauten Ausschnitten mit
ausgedachten Daten: `frontend/src/instagram/Update.tsx`, im Dev-Server unter
`http://localhost:5173/instagram-update.html` (`?s=1` bis `?s=5` für eine
einzelne Slide, `&f=story` für das Story-Format; ohne `f` entsteht dasselbe in
3:4). Der Rahmen ist mit dem ersten Beitrag geteilt (`Rahmen.tsx`).

Neu exportieren, während `npm run dev` in `frontend` läuft:

```bash
marketing/instagram-update/export.sh
```
