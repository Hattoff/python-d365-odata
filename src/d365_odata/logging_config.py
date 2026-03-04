import logging
from typing import Any

# Format log messages based on type
class LevelBasedFormatter(logging.Formatter):
    detailed_fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    debug_fmt = "%(name)s | %(message)s"
    simple_fmt = "%(message)s"

    def format(self, record):
        if record.levelno == logging.INFO:
            fmt = self.simple_fmt
        elif record.levelno == logging.DEBUG:
            fmt = self.debug_fmt
        else:
            fmt = self.detailed_fmt
        return logging.Formatter(fmt).format(record)

_LOGGING_CONFIGURED = False
_LOGGING_LOCK = __import__("threading").RLock()

def _parse_log_level(level: str | int) -> int:
    if isinstance(level, int):
        return level

    if not isinstance(level, str):
        raise TypeError("Log level must be str or int")

    try:
        return logging._nameToLevel[level.upper()]
    except KeyError:
        raise ValueError(f"Invalid log level: {level}")

def configure_logging(level:Any = "info") -> None:
    log_level = _parse_log_level(level)
    global _LOGGING_CONFIGURED
    with _LOGGING_LOCK:
        if _LOGGING_CONFIGURED:
            return

        handler = logging.StreamHandler()
        handler.setFormatter(LevelBasedFormatter())

        root = logging.getLogger()
        root.setLevel(log_level)

        # Avoid duplicate handlers if something else already configured logging
        if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
            root.addHandler(handler)

        _LOGGING_CONFIGURED = True
