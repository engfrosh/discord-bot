"""Discord Bot Client with EngFrosh specific features."""

from __future__ import annotations
import asyncio

import io
from typing import Any, Dict, Iterable, Optional, Set
import nextcord
from nextcord.ext import commands
import logging
import datetime as dt
import traceback

logger = logging.getLogger("EngFroshBot")

LOG_LEVELS = {
    "CRITICAL": 50,
    "ERROR": 40,
    "WARNING": 30,
    "INFO": 20,
    "DEBUG": 10,
    "NOTSET": 0
}


class EngFroshBot(commands.Bot):
    """Discord Bot Client with additional properties including config and error logging."""

    def __init__(self, command_prefix: str, config: Dict[str, Any],
                 help_command: Optional[str] = None, description: Optional[str] = None,
                 log_channels: Optional[Iterable[int]] = [],
                 **options):
        self.config = config
        if "debug" in config and config["debug"]:
            self.is_debug = True
        else:
            self.is_debug = False
        self.log_channels = log_channels
        self.background_tasks: Set[asyncio.Task] = set()
        super().__init__(command_prefix, description=description, **options)

    async def send_to_all(self, message: str, channels: Iterable[int], *,
                          purge_first: bool = False, file: Optional[nextcord.File] = None) -> bool:
        """Sends message to all channels with given ids."""
        res = True
        for chid in channels:
            if channel := self.get_channel(chid):
                if purge_first:
                    await channel.purge()
                await channel.send(message, file=file)
            else:
                logger.error(f"Could not get channel with id: {chid}")
                res = False

        return res

    async def _log(self, message: str, level: str = "INFO", exc_info=None) -> None:
        """Handler for logging to bot channel"""

        # Send to log channels
        content = f"\n{level} {dt.datetime.now().isoformat()}: {message}\n"
        if len(content) >= 1900:
            fp = io.StringIO(content)
            file = nextcord.File(fp, f"{dt.datetime.now().isoformat()}.log")
            await self.send_to_all("", self.log_channels, file=file)

        else:
            await self.send_to_all(f"```{content}```", self.log_channels)

    def log(self, message: str, level: str = "INFO", exc_info=None, *, print_to_console=False):
        """Log a message to the console, the logger, and the bot channels."""

        # Print to console
        if print_to_console:
            print(f"\n{level}: {message}")

        # Python Logger
        level = level.upper()
        if level in LOG_LEVELS:
            level_number = LOG_LEVELS[level]
        elif level == "EXCEPTION":
            logger.exception(message)
            return
        else:
            level_number = 0

        logger.log(level_number, message, exc_info=exc_info)

        # Send to log channels
        log_task = asyncio.create_task(self._log(message, level, exc_info=exc_info))
        self.background_tasks.add(log_task)
        log_task.add_done_callback(self.background_tasks.discard)

    async def on_error(self, event_method, *args, **kwargs):
        msg = f'Ignoring exception in {event_method}\n{traceback.format_exc()}'
        self.log(msg, "EXCEPTION")

    async def on_command_error(self, context, exception):
        trace = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        msg = f'Ignoring exception in command {context.command}:\n{trace}'
        self.log(msg, "EXCEPTION")

    def error(self, message, *, exc_info=None, **kwargs):
        self.log(message, "ERROR", exc_info=exc_info, **kwargs)

    def warning(self, message, *, exc_info=None, **kwargs):
        self.log(message, "WARNING", exc_info=exc_info, **kwargs)

    def info(self, message, *, exc_info=None, **kwargs):
        self.log(message, "INFO", exc_info=exc_info, **kwargs)

    def debug(self, message, *, exc_info=None, **kwargs):
        self.log(message, "DEBUG", exc_info=exc_info, **kwargs)
