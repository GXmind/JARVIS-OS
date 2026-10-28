"""Architecture contracts and application tests without real providers or devices."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import tempfile
import threading
import unittest

from jarvis.application.conversation import Conversation
from jarvis.application.ports import SessionServices
from jarvis.application.session import DesktopState
from jarvis.domain.errors import ServiceError
from jarvis.domain.settings import Settings
from jarvis.infrastructure.system.paths import ROOT
from jarvis.infrastructure.persistence.sqlite import Store
from jarvis.presentation.web.assets import read_asset

SOURCE=ROOT/"src/jarvis"

def imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node,ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node,ast.ImportFrom):
            if node.level:
                raise AssertionError(f"Use explicit package imports: {path.name}:{node.lineno}")
            yield node.module or ""

class ArchitectureTests(unittest.TestCase):
    def assert_dependencies(self,folder,allowed,blocked_stdlib=()):
        for path in (SOURCE/folder).rglob("*.py"):
            for module in imports(path):
                with self.subTest(file=str(path.relative_to(SOURCE)),dependency=module):
                    if module.startswith("jarvis"):
                        self.assertTrue(any(module==prefix or module.startswith(prefix+".") for prefix in allowed),module)
                    self.assertNotIn(module.split(".")[0],blocked_stdlib)

    def test_domain_has_no_io_or_outer_layer_dependencies(self):
        self.assert_dependencies("domain",("jarvis.domain",),
            ("sqlite3","tkinter","http","socket","subprocess","ctypes","pathlib","os"))

    def test_application_depends_only_on_ports_and_domain(self):
        self.assert_dependencies("application",("jarvis.application","jarvis.domain"),
            ("sqlite3","tkinter","http","socket","subprocess","ctypes","os"))

    def test_infrastructure_never_imports_presentation_or_bootstrap(self):
        self.assert_dependencies("infrastructure",("jarvis.infrastructure","jarvis.domain","jarvis.application"))

    def test_default_presentation_has_no_concrete_providers(self):
        # The platform window needs the fixed runtime path. Archived Tkinter has a documented exception.
        for folder in ("presentation/web","presentation/desktop"):
            self.assert_dependencies(folder,("jarvis.presentation","jarvis.application","jarvis.domain","jarvis.infrastructure.system.paths"))

    def test_imports_resolve_to_owned_modules(self):
        for path in SOURCE.rglob("*.py"):
            for module in imports(path):
                if not module.startswith("jarvis"):continue
                target=ROOT/"src"/module.replace(".","/")
                self.assertTrue(target.with_suffix(".py").is_file() or (target/"__init__.py").is_file(),module)

    def test_static_assets_cannot_escape_root(self):
        for path in ("/../config/.env","/%2e%2e/config/.env","/rendering/../../../../config/.env","/C:/Windows/win.ini","/rendering%5c..%5cconfig.env","/index.html","/missing.js"):
            with self.subTest(path=path):self.assertIsNone(read_asset(path))

    def test_canonical_and_compatibility_assets_are_served(self):
        for path in ("/","/app.js","/core/client.js","/ui/settings.js","/rendering/energy.js","/rendering/shaders.js","/rendering/city_geometry.js","/features/navigation/controller.js","/features/navigation/sdk.js","/features/navigation/routes.js","/features/map/controls.js","/styles/main.css","/navigation.js","/city.js","/scene.js"):
            with self.subTest(path=path):self.assertIsNotNone(read_asset(path))
        self.assertIn('type="module"',read_asset("/")[0])
        self.assertTrue(read_asset("/")[2])
        self.assertIn('/features/navigation/controller.js',read_asset("/navigation.js")[0])

class ApplicationPortsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/"tmp")
        self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/"ports.sqlite3")

    def test_cloud_reply_uses_injected_gateway_and_saves_history(self):
        gateway=Mock();gateway.chat.return_value="先生，路线交给导航服务核对。"
        factory=Mock(return_value=gateway)
        service=Conversation(self.store,cloud_factory=factory)
        settings=Settings(CHAT_MODE="api")
        sid=self.store.new_session()
        answer,_=service.reply(sid,"你好",settings)
        factory.assert_called_once_with(settings)
        self.assertEqual(gateway.chat.call_args.args[0][-1],{"role":"user","content":"你好"})
        self.assertEqual(self.store.history(sid)[-1]["content"],answer)

    def test_missing_cloud_wiring_is_explicit(self):
        with self.assertRaisesRegex(ServiceError,"尚未装配"):
            Conversation(self.store).reply(self.store.new_session(),"你好",Settings(CHAT_MODE="api"))

    def services(self):
        audio=SimpleNamespace(capture_active=False,level=0,stop_event=threading.Event(),stop=Mock(),close=Mock())
        weather=SimpleNamespace(reset=Mock(),snapshot=Mock(return_value={}),accept_live=Mock())
        return SessionServices(self.store,audio,Mock(),Mock(),weather,SimpleNamespace(sample=lambda:{}))

    def test_session_uses_repository_counts_without_sql_connection(self):
        services=self.services()
        state=DesktopState(Settings(),services)
        # The application sees a repository interface, never a raw SQL connection.
        self.store.connect=Mock(side_effect=AssertionError("Raw database access in application"))
        self.store.counts=Mock(return_value={"memories":3,"messages":8})
        self.assertEqual(state.snapshot()["counts"],{"memories":3,"messages":8})
        self.store.counts.assert_called_once_with(state.sid)

    def test_settings_persist_through_injected_writer_and_preserve_secret(self):
        services=self.services();state=DesktopState(Settings(API_KEY="synthetic-key"),services)
        state.config_save({"API_KEY":"","WEATHER_CITY":"苏州虎丘区","MAP_HEIGHT_SCALE":"20"})
        services.save_settings.assert_called_once_with(state.settings)
        self.assertEqual(state.settings.API_KEY,"synthetic-key")
        self.assertEqual(state.config_public()["API_KEY"],"")
        services.weather.reset.assert_called_once_with("苏州虎丘区")

    def test_session_close_stops_then_releases_audio(self):
        services=self.services();state=DesktopState(Settings(),services)
        order=[];services.audio.stop.side_effect=lambda:order.append("stop")
        state.wait_workers=Mock(side_effect=lambda _:order.append("wait"))
        services.audio.close.side_effect=lambda:order.append("close")
        state.close()
        self.assertEqual(order,["stop","wait","close"])
        self.assertTrue(state.closed.is_set())