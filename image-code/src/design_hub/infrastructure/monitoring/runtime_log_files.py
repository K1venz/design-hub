import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

import sentry_sdk

RuntimeLogService = Literal["api", "worker"]

_error_report_lock = threading.Lock()
_error_reported = False


def is_business_chain_record(record: logging.LogRecord) -> bool:
    chain = getattr(record, "chain", None)
    action = getattr(record, "action", None)
    return (
        record.name.startswith("design_hub.")
        and isinstance(chain, str)
        and bool(chain)
        and isinstance(action, str)
        and bool(action)
    )


class BusinessChainFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return is_business_chain_record(record)


class RuntimeBusinessLogHandler(RotatingFileHandler):
    def handleError(self, record: logging.LogRecord) -> None:
        del record
        error = sys.exc_info()[1]
        if isinstance(error, BaseException):
            try:
                sentry_sdk.capture_exception(error)
            except Exception:
                pass
        global _error_reported
        with _error_report_lock:
            if _error_reported:
                return
            _error_reported = True
        try:
            sys.stderr.write("runtime business log write failed\n")
        except Exception:
            pass


def runtime_log_handler(
    directory: Path,
    service: RuntimeLogService,
    max_bytes: int,
) -> logging.Handler:
    directory.mkdir(parents=True, exist_ok=True)
    handler = RuntimeBusinessLogHandler(
        directory / f"{service}.jsonl",
        maxBytes=max_bytes,
        backupCount=1,
        encoding="utf-8",
    )
    handler.addFilter(BusinessChainFilter())
    return handler
