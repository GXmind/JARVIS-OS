# Third-party notices

- **Three.js r180** — https://threejs.org/ — MIT license. Vendored in src/jarvis/presentation/web/assets/vendor; retain THREE-LICENSE.txt and the upstream headers.
- **eviltransform** — https://github.com/googollee/eviltransform — BSD license. Vendored Python coordinate conversion and license in src/jarvis/infrastructure/vendor.
- **OpenStreetMap contributors** — https://www.openstreetmap.org/copyright — map data under ODbL. Attribution remains visible in the navigation scene.
- **OpenFreeMap / OpenMapTiles** — https://openfreemap.org/ and https://openmaptiles.org/ — providers of vector tiles used for the local city; data attribution and applicable service terms remain in force.
- **AMap / 高德** — https://www.amap.com/ — online SDK, POI, route and weather services. Not redistributed as part of this source repository; credentials, permissions, quotas and the provider's terms apply.
- Optional sounddevice / PortAudio dependencies are installed separately; their respective licenses apply.

The repository's Apache-2.0 license applies to original project code and does not replace third-party licenses.


- Optional **MediaPipe Tasks Vision 0.10.21** — https://github.com/google-ai-edge/mediapipe — Apache-2.0 code, downloaded from the official npm package. Hand Landmarker model bundle is downloaded from Google's mediapipe-models distribution; model documentation/card: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker . Versioned URLs and SHA-256 digests are recorded in config/hand-runtime.json. Downloaded runtime/model assets are kept in the user's project-local cache and are not redistributed in this repository.

- Optional **Vosk API 0.3.45** and **vosk-model-small-en-us-0.15** — https://alphacephei.com/vosk/ and https://alphacephei.com/vosk/models — Apache-2.0. Offline wake-only recognition; package installed separately, model version/URLs/SHA-256 recorded in config/wake-runtime.json. Package dependencies retain their own licenses. Model/cache files are not redistributed in this repository.
