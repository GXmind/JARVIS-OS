"""Literal .env persistence. No interpolation, execution or OS secret lookup."""
from dataclasses import asdict
import json
import os
from jarvis.domain.settings import Settings
from jarvis.infrastructure.system.paths import ROOT, local_path

DEFAULT_ENV=ROOT/"config/.env"

def load_settings(path=DEFAULT_ENV):
    path = local_path(path)
    data = {}
    defaults = asdict(Settings())
    if path.exists():
        for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if not sep:
                raise ValueError(f".env 第 {n} 行缺少等号。")
            if key not in defaults:
                continue
            if value.startswith('"'):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    raise ValueError(f".env 第 {n} 行引号格式错误。") from None
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            if not isinstance(value, str):
                raise ValueError(f".env 第 {n} 行需要字符串。")
            data[key] = value
    return Settings(**data).validated()


def save_settings(settings, path=DEFAULT_ENV):
    settings.validated()
    path = local_path(path)
    temporary = path.with_suffix(".env.tmp")
    text = "# JARVIS settings; contains secrets. Do not share this file.\n"
    text += "\n".join(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in asdict(settings).items()) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
