# DialoStack GUI architecture

A single-page React app (Vite + Tailwind) to **configure, launch and monitor**
DialoStack dialogues. It talks to two backends:

- **The GUI server** (`../server.py`) over HTTP (`lib/api.js`). It generates the
  ROS parameter YAML, serves engine defaults (prompts, phrases), starts and stops
  the engine, and exposes mic and system helpers. **All YAML/param generation lives
  in the server, never in the frontend.**
- **rosbridge** over WebSocket (roslib) for live ROS topics and the dialog action,
  via the hooks in `hooks/`.

```
src/
├── main.jsx            Entry: mounts providers (Engine, ROS, Config) + router
├── App.jsx             Shell: sidebar + routes + the shared dialogue timeline
├── components/         Shared UI, built from here, not redefined per page
│   ├── ui.jsx          Form atoms (Field, Select, NumberField…), ModifiedTag, badges
│   ├── FileImportButton.jsx, Sidebar.jsx, ConnectionBadge.jsx, EngineNotices.jsx
├── contexts/           Cross-page global state
│   ├── ConfigContext   The whole config object (localStorage-backed) + updateSection
│   ├── EngineContext   Engine status polling, start/stop/killAll, keepalive
│   └── ROSContext      rosbridge connection
├── hooks/              Reusable React/IO logic
│   ├── useTopic / usePublisher / useActionClient   ROS plumbing
│   ├── useDialogTimeline                            Topics → timeline reducer actions
│   ├── usePersistentState / usePopover / useFlash / useLlmError / useImageTopic(s)
├── lib/                Pure logic + constants (unit-tested with *.test.js)
│   ├── api.js          The ONLY HTTP client (timeouts, typed ApiError)
│   ├── ros.js          Topic/action names + types (single source)
│   ├── formatters.js   Time/duration formatting (shared by Monitor + export)
│   ├── prompts.js / strategies.js   Editor metadata + validation/grouping
│   ├── frames.js       Frame Builder data layer + Builder↔page handoff
│   ├── sessionExport.js  Timeline → CSV/JSON/Markdown
│   ├── storageKeys.js  localStorage keys (single source)
│   └── timeline/reducer.js  Pure Monitor state machine (no React/ROS, fully tested)
└── pages/              One folder per route
    ├── Monitor/        Chat timeline, launch drawer, composer, frame sidebar
    ├── FrameBuilder/   Build a frame per strategy (slots / quiz / resources)
    ├── PromptsEditor/  Override the LLM prompt templates
    ├── StrategiesEditor/  Edit each strategy's canned phrases (per language)
    └── ConfigEditor/   Parameter tabs (LLM, Dialogue, STT, TTS, Audio) + engine panel
```

## Data flow

**Config → engine.** Editors write into `config.<section>` via
`updateSection` (ConfigContext, persisted to localStorage). On engine start,
`EngineContext` POSTs the whole config. `server.py` turns it into a ROS params
file and launches the engine. The frontend never builds YAML.

**ROS → screen.** `useDialogTimeline` subscribes to the dialog topics/feedback
and dispatches actions into the pure `timeline/reducer.js`. The Monitor renders
the resulting `events`. Time and parsing enter only through actions, so the
reducer is testable without React or ROS.

**Editable engine resources (prompts, phrases)** follow one pattern: defaults
come from the engine (`/api/{prompts,phrases}`), the user edits *overrides*
stored in `config.{prompts,phrases}`, and on start the server injects only the
valid, changed ones as node parameters (defaults always win otherwise).

## How to…

- **Add a config parameter:** default it in `ConfigContext` `DEFAULT_CONFIG`,
  add a field in the matching `ConfigEditor/<Tab>.jsx` calling
  `update({ key: value })`, and map it to a ROS param in `server.py`'s
  `build_params`.
- **Add a page:** create `pages/<Name>/index.jsx`, route it in `App.jsx`, and
  add it to `PAGES` in `components/Sidebar.jsx`.
- **Add a ROS topic:** add it to `TOPICS` in `lib/ros.js`, then
  `useTopic(name, type, cb)` (or `usePublisher`) where needed.
- **Add an editable phrase/prompt:** add it to the engine's defaults
  (`ros2_dialog_manager`), expose via the existing `/api/{prompts,phrases}`
  endpoints, and it shows up in the corresponding editor automatically.

## Conventions

- Pure logic and constants live in `lib/`. UI primitives live in `components/ui.jsx`,
  IO and stateful logic in `hooks/`, and global state in `contexts/`.
- Use `usePersistentState` for anything that should survive a reload.
- All server calls go through `lib/api.js` (don't `fetch` directly).
- `npm test` runs the `lib/*.test.js` unit tests. `npm run build` compiles the app.
  Keep both green.
