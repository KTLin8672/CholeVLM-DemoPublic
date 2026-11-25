# Changelog

What changed in the demo, by date, oldest first.

## 2026-11-05

- The first version: a web page (Vite and plain three.js) served by a small Starlette server on 127.0.0.1, built against a made-up test feed, and a test that the repository loads no model and reads no dataset file.
- The page reads the evaluation and serving repository's API, at a pinned version (0.1, then 1.0, then 1.2): the model's decisions, its frames at 1 fps, and the video by byte ranges.
- A video player synced to the model's decisions by video time, with an inset of the frame the model saw.
- A presenter view by default and an engineer view with the raw replies and every delay figure; alerts pinned and loud, butter and red kept for severity alone.
- The page redrawn as a 3D operating room: the video on the endoscope monitor, the model's reading on a boom monitor, an alarm beacon, and a blob perched on the video's monitor.
- Laparoscopic instruments in the room: four trocars and the instruments through them.
- Public and read-only through ngrok: only the listed videos, per-visitor rate limits, not indexed, no referrer, and the dataset's attribution with "research demo, not for clinical use" on every frame of a real video; nothing about the machine is served.
- Asking the model is the owner's alone, behind a password kept as a scrypt hash in a gitignored file; a visitor can only watch.

## 2026-11-06

- `record`: the page rendered frame by frame into an H.264 video, with a JSON file beside it.
- A run still being written is followed through one socket for every viewer, with reconnects; every decision is kept in a session log as it arrives; a frozen frame, a late decision and the fall-back state are shown as such.
- The delay figures labelled by what they count: "live would skip" and "replies over D".
- A video from a hospital the model never trained on, labelled so on every frame, and shown only after sign-in until its licence is known to allow public display.
- The room made live (the beacon's sweep, the blob's gaze, the video monitor's glow) and given more equipment: an electrosurgical generator, wall suction, infusion pumps, dispensers and a linen hamper, every cable running from its instrument to its device, and each device's screen showing its own settings, never the patient's.
- Realistic surfaces: reflections from the room's own lights, finishes that vary across each surface, ambient occlusion, and the video drawn untouched on top.
- The room turns by dragging, up to 40° either way round the vertical axis; a double click faces it again.
- The demo shows exactly three videos, in a fixed order.
- `tenant`: heavy CPU work (the browser tests, renders and recordings) runs in a capped scope beside a training job, and stops if the training step slows.

## 2026-11-07

- The room is drawn only as often as it changes (a few frames a second while the video plays, none while hidden), since drawing every frame slowed a training job on the same GPU.
- A phone view: the camera square-on to the video's monitor, the model's reading as a dashboard under the room, every control at least 44 px.
- The sign-in moved to an Owner tab beside Presenter and Engineer; Sign out drops this browser's cookie.
- One run a video: the newest checkpoint's finished run over the whole video, and of those the fullest.
- A run written in a newer API version than the pin is not listed.

## 2026-11-09

- The API pinned at 1.7: the engineer view shows the vision probe's numbers, the checkpoint and its gate, and the event box gains "unfamiliar scene".
- The monitors rearranged, left to right: the video; the tools in view now and next, each pictured from a 3D model drawn ahead of time by `bake-instruments`; the model's reading with the beacon.
- On a phone, the tools are a card above the room.
- The gate's verdict on the engineer's page is read from its figures alone.

## 2026-11-10

- The API pinned at 1.9: its new fields are read and cut away, nothing new drawn.
- The test feed's live runs start at their first viewer.

## 2026-11-12

- The API pinned at 1.10; the prior's text is no longer passed to the page.

## 2026-11-14

- The reading as a navigation aid: what is coming leads (the next phase and the next instrument with their countdowns, the instruments' chance within five minutes), each with its source; the 30-second next step is on the engineer's page.
- The API pinned at 1.12: each served CVS criterion with where its value came from.

## 2026-11-17

- The served CVS drawn as a screening signal, "not seen" or "possibly seen", never as a criterion met.

## 2026-11-18

- The model's own CVS reading is cut from everything the server sends, and the running memory to what the page draws.
- The API pinned at 1.13: each served criterion's precision, NPV and share met on the validation set, on the engineer's page.

## 2026-11-22

- The bleeding flag, never scored, is drawn as "unscored": an outline, no red, no beacon.
- The tools monitor's right half: the two tools the model called most over the last three minutes.
- The patient on a split-leg table, the head intubated behind a linen anaesthesia screen.

## 2026-11-23

- The reading monitor: now on the left, what is ahead on the right.
- The page is sent with `Cache-Control: no-cache`, so a new build shows at the next load.
- The tools monitor without the call counts; they are on the engineer's page.
- README.md rewritten as how to operate the repository; `requirements.txt` and `requirements-dev.txt` pin the Python packages.

## 2026-11-24

- The README's ship block swaps in a build only once its tests pass and says which happened; `record` refuses to record over a recording without `--replace`.
- A screenshot of the live page in the README.
- The phone's dashboard reads as the reading monitor does: now, safety, the model's words, then what is ahead.
- The animation guide matches the page's anchors and a decision's fields.
- The first public version.
