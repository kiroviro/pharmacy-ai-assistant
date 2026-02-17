"""
Logging configuration for ViaPharma chatbot.

Provides structured logging with support for:
- JSON format for production
- Human-readable format for development
- Request ID tracking
- Performance metrics
"""

import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC
from functools import wraps

# Context variable for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RequestIdFilter(logging.Filter):
    """Add request ID to log records."""

    def filter(self, record):
        record.request_id = request_id_var.get() or "-"
        return True


class ViaPharmaFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    def format(self, record):
        # Add color based on level
        colors = {
            "DEBUG": "\033[36m",  # Cyan
            "INFO": "\033[32m",  # Green
            "WARNING": "\033[33m",  # Yellow
            "ERROR": "\033[31m",  # Red
            "CRITICAL": "\033[35m",  # Magenta
        }
        reset = "\033[0m"
        color = colors.get(record.levelname, "")

        # Format: timestamp | LEVEL | request_id | module | message
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        request_id = getattr(record, "request_id", "-")

        return (
            f"{timestamp} | {color}{record.levelname:8}{reset} | "
            f"{request_id[:8]:8} | {record.module:20} | {record.getMessage()}"
        )


class JsonFormatter(logging.Formatter):
    """JSON formatter for production logging."""

    def format(self, record):
        import json

        log_data = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%f"),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "request_id",
                "message",
            ):
                log_data[key] = value

        return json.dumps(log_data, ensure_ascii=False, default=str)


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: str | None = None,
) -> logging.Logger:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON format (for production)
        log_file: Optional file path for logging

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("viapharma")
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Create formatter
    if json_format:
        formatter = JsonFormatter()
    else:
        formatter = ViaPharmaFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RequestIdFilter())
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JsonFormatter())  # Always JSON for files
        file_handler.addFilter(RequestIdFilter())
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str = "viapharma") -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


def set_request_id(request_id: str | None = None) -> str:
    """Set the request ID for the current context."""
    if request_id is None:
        request_id = uuid.uuid4().hex[:8]
    request_id_var.set(request_id)
    return request_id


def get_request_id() -> str:
    """Get the current request ID."""
    return request_id_var.get() or ""


def log_timing(logger: logging.Logger | None = None):
    """Decorator to log function execution time."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = get_logger()

            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                logger.debug(f"{func.__name__} completed", extra={"duration_ms": round(duration_ms, 2)})
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000
                logger.error(f"{func.__name__} failed: {e}", extra={"duration_ms": round(duration_ms, 2)})
                raise

        return wrapper

    return decorator


# Initialize default logger on module import
_default_logger: logging.Logger | None = None


def init_default_logger(level: str = "INFO", json_format: bool = False):
    """Initialize the default logger (call once at startup)."""
    global _default_logger
    _default_logger = setup_logging(level=level, json_format=json_format)
    return _default_logger


# =============================================================================
# Audit Logging for Medical Queries (Regulatory Compliance)
# =============================================================================

_audit_logger: logging.Logger | None = None


def get_audit_logger() -> logging.Logger:
    """
    Get the audit logger for medical query tracking.

    Audit logs are always JSON format and written to a separate file
    for compliance and liability purposes.
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = logging.getLogger("viapharma.audit")
        _audit_logger.setLevel(logging.INFO)
        _audit_logger.handlers.clear()

        # Always use JSON formatter for audit logs
        formatter = JsonFormatter()

        # Console handler for audit logs
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(RequestIdFilter())
        _audit_logger.addHandler(console_handler)

        # File handler for persistent audit trail
        from pathlib import Path

        audit_dir = Path("logs/audit")
        audit_dir.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(audit_dir / "medical_queries.jsonl", encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(RequestIdFilter())
        _audit_logger.addHandler(file_handler)

        _audit_logger.propagate = False

    return _audit_logger


def log_medical_query(
    query_hash: str,
    is_medical: bool,
    is_red_flag: bool,
    products_recommended: list[str],
    safety_severity: str,
    response_length: int,
    client_ip_hash: str = "",
    duration_ms: float = 0.0,
):
    """
    Log a medical query for audit purposes.

    Privacy-preserving: logs hashes instead of actual query content.

    Args:
        query_hash: SHA256 hash of the user query (privacy-preserving)
        is_medical: Whether the query was classified as medical
        is_red_flag: Whether red-flag symptoms were detected
        products_recommended: List of product SKUs recommended
        safety_severity: Safety check severity level
        response_length: Length of the response
        client_ip_hash: Hashed client IP (privacy-preserving)
        duration_ms: Request processing time
    """
    from datetime import datetime

    audit = get_audit_logger()
    audit.info(
        "medical_query_processed",
        extra={
            "event_type": "medical_query",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "query_hash": query_hash,
            "client_ip_hash": client_ip_hash,
            "is_medical": is_medical,
            "is_red_flag": is_red_flag,
            "safety_severity": safety_severity,
            "products_count": len(products_recommended),
            "products_skus": products_recommended[:5],  # Limit to first 5
            "response_length": response_length,
            "duration_ms": round(duration_ms, 2),
        },
    )


def hash_for_audit(text: str) -> str:
    """Create a privacy-preserving hash for audit logging."""
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:16]
