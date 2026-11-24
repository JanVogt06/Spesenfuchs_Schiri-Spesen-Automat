# Instagram story: update since the introduction

Five story slides in 9:16 format (1080 × 1920) about everything that has been
added since the introduction post in September. Upload as a story in this
order:

1. `01-update.png` – Stoppage time with news (update)
2. `02-beobachtungen.png` – Your grades at a glance (the *Beobachtungen*, i.e. observations, tab)
3. `03-app.png` – Onto the home screen (installable, tab bar)
4. `04-feinschliff.png` – On mobile it's now a home game (tap contacts,
   larger fields, key figures side by side, message when offline)
5. `05-aufruf.png` – Just reload (call to action)

Space is left at the top and bottom for Instagram's bars. On the last slide,
a gap is left free below the address: place the **link sticker** with
`https://spesenfuchs.jan-vogt.dev` there (sticker icon → Link). So the story
does not disappear after 24 hours, it can stay on the profile as a highlight
("Updates").

Like the first post, it is built from recreated excerpts with made-up data:
`frontend/src/instagram/Update.tsx`, in the dev server at
`http://localhost:5173/instagram-update.html` (`?s=1` to `?s=5` for a single
slide, `&f=story` for the story format; without `f` the same is rendered in
3:4). The frame is shared with the first post (`Rahmen.tsx`).

To export again while `npm run dev` is running in `frontend`:

```bash
marketing/instagram-update/export.sh
```
