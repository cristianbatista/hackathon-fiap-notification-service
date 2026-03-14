import json
import logging
import sys
import uuid
from datetime import UTC, datetime


class JSONFormatter(logging.Formatter):
    SERVICE_NAME = "notification-service"

    def format(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, "trace_id", str(uuid.uuid4()))
        job_id = getattr(record, "job_id", None)
        recipient = getattr(record, "recipient", None)
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "service": self.SERVICE_NAME,
            "level": record.levelname,
            "message": record.getMessage(),
            "trace_id": trace_id,
        }
        if job_id:
            log_entry["job_id"] = job_id
        if recipient:
            # Log only the domain part for security — never the full address
            domain = recipient.split("@")[-1] if "@" in recipient else "unknown"
            log_entry["recipient_domain"] = domain
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        root.addHandler(handler)
    root.setLevel(level.upper())
