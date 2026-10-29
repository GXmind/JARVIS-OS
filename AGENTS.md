# Repository collaboration instructions

- Read CONTRIBUTING.md, BUILDING.md, docs/API_SETUP.md and docs/architecture.md before changing the corresponding area.
- Runtime files must stay under F:\Javis_os. Preserve fixed-root startup checks and project-local caches.
- Preserve existing configuration, recordings, databases, logs and uncommitted work. Never publish them.
- Keep config/.env private; template credentials stay empty. Public fixtures use synthetic or public locations, never residential addresses.
- Respect the user-requested branch and synchronization scope. feature/map-update was merged by PR #1. Use current code and merge history for release state; do not infer that a branch is pending from its name. Explicit user authorization to sync main is sufficient; this file adds no extra approval step.
- Follow layered boundaries: domain is pure; application uses domain and ports; infrastructure implements external services; presentation handles transport and interaction. Production wiring belongs in bootstrap.py.
- New business code must not import concrete CloudAPI/Audio/Store into application or execute SQL there. Inject SessionServices/HttpServices; keep persistence and provider details in infrastructure.
- New frontend code belongs under presentation/web/assets core, ui, features or rendering. Keep pure geometry separate from GPU resources. Do not restore flat duplicate modules or put new features in presentation/legacy.
- Update module imports, diagnostics, scripts, dependency tests and architecture documentation together when moving code. Keep CLI, HTTP contracts and user data formats stable unless explicitly changing them.
- Run relevant unittest and npm tests. Structural/render changes also require actual Chromium and map pressure checks. Distinguish live provider checks from fixtures and device-call success from confirmed audible quality.
- Do not invent successful navigation, building data or trained emotion models. Preserve attribution and third-party licenses.
- Never force-push or rewrite shared history. Inspect remote changes before synchronization. Review staged files and secrets before publishing.

- For hand tracking, keep frames local and the camera off by default. Stop tracks/workers on disable, hidden primary, disconnect and exit; test cancellation and backpressure. Never publish camera images or downloaded model caches.
- Voice and camera input belong only to the primary. A transferred map owns an independent controller, view and close action; primary dialogue/new navigation/closing navigation must never mutate or close it. Freeze the transfer seed, reject stale window epochs and bound the explicit camera mailbox. Restricted map capabilities must reject recording, dialogue, settings and global shutdown. Verify departure/arrival particles and distinguish one-monitor checks from physical extended-display validation.

- Wake listening stays offline and shares the audio lock with command capture. Pause and release the listener before recording, resume after response; never save/upload ambient PCM. Test synthesized decoder behavior separately from real human accuracy.
- Map transfer must prewarm hidden, finish primary departure before revealing destination, and gate controls until assembly completes. Test native hidden-window scheduling and strict stages; never rewind independent state on a late ready. Geometry workers coalesce pending views and reject stale results.

- Free visual prompts must reach the cloud designer in full. Never substitute built-in objects in cloud mode; reserve them for explicit offline demos. Descriptive edits retain scene context. F4 routes arbitrary prompts without requiring object keywords.
- Generated visuals are validated data only: paths, vertices, patches, profiles and bounded transform tracks. Do not execute generated code, SVG documents or external resources. Keep sampling, queues and buffers bounded; do not repeat unchanged scene geometry in polling.
- Preserve dedicated map/model visual priority, independent secondary maps, real render acknowledgements and cancellation. Verify streamed speech with one output device and distinguish measured first-token/first-audio latency from human sound quality.
