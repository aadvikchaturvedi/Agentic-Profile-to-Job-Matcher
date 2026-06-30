import sys
from loguru import logger


def setup_logging() -> None:
    logger.remove()

    logger.add(
        sys.stdout,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <7}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
            "<level>{message}</level>"
        ),
        level="INFO",
        colorize=True,
    )

    logger.add(
        "logs/agentic-matcher.log",
        rotation="10 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name}:{function} | {message}",
        level="DEBUG",
    )

    logger.info("Logging configured")
