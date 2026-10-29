"""Composition root: the only place wiring the production assistant services."""
from jarvis.domain.settings import Settings
from jarvis.application.ports import SessionServices
from jarvis.application.session import DesktopState
from jarvis.infrastructure.http.openai_compatible import CloudAPI
from jarvis.infrastructure.audio.service import Audio, devices
from jarvis.infrastructure.audio.wake import WakeListener
from jarvis.infrastructure.config.env_file import save_settings
from jarvis.infrastructure.persistence.sqlite import Store
from jarvis.infrastructure.weather.provider import Weather
from jarvis.infrastructure.system.telemetry import Telemetry
from jarvis.infrastructure.maps.amap import fetch_proxy
from jarvis.infrastructure.maps.city_context import city_context
from jarvis.presentation.web.server import DesktopServer, HttpServices
from jarvis.presentation.desktop.window import native_drag, run
from jarvis.presentation.desktop.map_windows import MapWindows
from jarvis.infrastructure.vision.runtime import status as hand_status, read_asset as hand_asset

def create_state(settings: Settings, store=None, *, services: SessionServices | None = None):
    if services is None:
        services=SessionServices(store=store if store is not None else Store(), audio=Audio(),
            cloud_factory=CloudAPI, save_settings=lambda value: save_settings(value),
            weather=Weather(settings.WEATHER_CITY), telemetry=Telemetry(),wake_factory=WakeListener)
    elif store is not None:
        raise ValueError("提供 services 后不能再单独指定 store。")
    return DesktopState(settings,services)

def create_server(state, *, services: HttpServices | None = None):
    if services is None:
        services=HttpServices(fetch_proxy=lambda *args: fetch_proxy(*args),
            city_context=city_context, devices=devices, drag=native_drag,
            map_windows=MapWindows(),hand_status=hand_status,hand_asset=hand_asset)
    return DesktopServer(state,services)

def run_desktop(settings, config_error=None):
    state=create_state(settings)
    server=create_server(state)
    state.audio.warmup(settings)
    state.start_voice()
    return run(state,server,config_error)
