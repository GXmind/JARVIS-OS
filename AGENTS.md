# Repository collaboration instructions

- Read CONTRIBUTING.md, BUILDING.md, docs/API_SETUP.md and docs/architecture.md before changing the corresponding area.
- Runtime files must stay under F:\Javis_os. Preserve the fixed-root startup checks and project-local caches.
- Keep existing user configuration, recordings, databases, logs and uncommitted work. Never copy these into a public commit.
- Treat config/.env and provider credentials as private. Keep the template credential fields empty. Public fixtures use synthetic or public locations, never residential addresses.
- Respect the requested branch. feature/map-update contains the map improvements; a documentation update on main is not authorization to merge the feature.
- Keep changes reviewable and tests relevant. Verify Python logic with unittest, frontend geometry/interaction with npm test, and rendering with the actual browser check when UI behavior changes.
- Distinguish live provider checks from synthetic fixtures and device-call success from confirmed audible quality.
- Do not invent successful tool execution, navigation, building data or trained emotion models. Preserve data-source attribution and third-party licenses.
- Routine reversible work within the user's request can proceed; this file does not add a separate approval step.
