"""Logging configuration for Agent execution tracking."""

import logging
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_FILE = Path("logs/app.log")


def get_agent_logger(name: str) -> logging.Logger:
    """Get or configure a logger that writes to logs/app.log."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Ensure log directory exists
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Check if FileHandler already exists for app.log to avoid duplicates
    has_file_handler = False
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler) and handler.baseFilename.endswith("app.log"):
            has_file_handler = True
            break

    if not has_file_handler:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(file_handler)

    # Cảnh báo/lỗi phải ra CẢ stdout, không chỉ `logs/app.log`.
    #
    # `app.log` nằm TRONG container và không được mount ra ngoài, nên nó mất theo
    # mỗi lần dựng lại image, và mọi công cụ đọc log tiêu chuẩn (`docker logs`,
    # thu gom log tập trung) không thấy gì. Điều tra sự cố 2026-08-26 mất một
    # vòng vì `docker logs` trả 14.176 dòng mà KHÔNG dòng nào của agent — cảnh
    # báo guardrail đã được ghi đúng, chỉ là ghi vào chỗ không ai nhìn.
    #
    # Chỉ WARNING trở lên: INFO của agent rất dày (mỗi lượt vài dòng), đẩy hết ra
    # stdout thì nhấn chìm log truy cập của web server. File vẫn giữ đủ INFO.
    has_stream_handler = any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
        for handler in logger.handlers
    )
    if not has_stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.WARNING)
        stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(stream_handler)

    return logger


def log_file_execution(file_name: str, logger: logging.Logger | None = None) -> None:
    """Log clearly when starting execution of a specific file."""
    log = logger or get_agent_logger("agent.execution")
    log.info("Starting execution of %s", file_name)
