from loguru import logger


async def graceful_shutdown() -> None:
    logger.info("Shutting down — cleaning up resources")
