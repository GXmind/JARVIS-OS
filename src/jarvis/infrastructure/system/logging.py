import logging
from logging.handlers import RotatingFileHandler
import re
from jarvis.infrastructure.system.paths import ROOT

class SecretFilter(logging.Filter):
    def filter(self, record):
        # Application code logs event categories only; this is additional redaction.
        text = record.getMessage()
        text = re.sub(r"(?i)Bearer\s+\S+", "Bearer [REDACTED]", text)
        text = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", text)
        record.msg, record.args = text, ()
        return True

def configure_logging():
    logger = logging.getLogger("jarvis")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(ROOT / "logs/jarvis.log", maxBytes=1_000_000,
                                      backupCount=3, encoding="utf-8")
        handler.addFilter(SecretFilter())
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger