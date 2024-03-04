"""Discord Bot Client with EngFrosh specific features."""

from __future__ import annotations
import asyncio

import io
from typing import Any, Dict, Optional, Set
import nextcord
from nextcord import Interaction
from nextcord.ext import commands, application_checks
from nextcord.utils import get
from nextcord.errors import ApplicationCheckFailure
import logging
import datetime as dt
import traceback
from common_models.models import DiscordUser
from asgiref.sync import sync_to_async
from random import randrange
from django.db import close_old_connections

logger = logging.getLogger("EngFroshBot")

LOG_LEVELS = {
    "CRITICAL": 50,
    "ERROR": 40,
    "WARNING": 30,
    "INFO": 20,
    "DEBUG": 10,
    "NOTSET": 0
}

instance = None

global_config = {}


def is_admin():
    def predicate(i: nextcord.Interaction):
        member = i.user
        superadmin = global_config['module_settings']['management']['superadmin']
        if i.user.id in superadmin:
            return True
        if member.guild_permissions >= nextcord.Permissions(administrator=True):
            return True
        admin_roles = global_config['admin_roles']
        for r in admin_roles:
            if get(member.roles, id=r) is not None:
                return True
        return False
    return application_checks.check(predicate)


def is_superadmin():
    def predicate(i: nextcord.Interaction):
        superadmin = global_config['module_settings']['management']['superadmin']
        if i.user.id in superadmin:
            return True
        return False
    return application_checks.check(predicate)


def has_permission(perm):
    def predicate_sync(member):
        close_old_connections()
        if member.guild_permissions >= nextcord.Permissions(administrator=True):
            return True
        user = member.id
        superadmin = global_config['module_settings']['management']['superadmin']
        if user in superadmin:
            return True
        discord_user = DiscordUser.objects.filter(id=user).first()
        if discord_user is None:
            return False  # User account isn't linked
        user_model = discord_user.user
        if user_model.is_superuser:
            return True
        return user_model.has_perm(perm)

    async def predicate(i: nextcord.Interaction):
        return await sync_to_async(predicate_sync)(i.user)
    return application_checks.check(predicate)


class EngFroshBot(commands.Bot):
    """Discord Bot Client with additional properties including config and error logging."""

    def __init__(self, config: Dict[str, Any],
                 help_command: Optional[str] = None, description: Optional[str] = None,
                 log_channel: Optional[int] = [],
                 **options):
        self.config = config
        if "debug" in config and config["debug"]:
            self.is_debug = True
        else:
            self.is_debug = False
        self.log_channel = log_channel
        self.background_tasks: Set[asyncio.Task] = set()
        global global_config
        global_config = config
        super().__init__(description=description, default_guild_ids=[config['guild']], **options)

    async def _log(self, message: str, level: str = "INFO", exc_info=None) -> None:
        """Handler for logging to bot channel"""

        # Send to log channels
        content = f"\n{level} {dt.datetime.now().isoformat()}: {message}\n"
        guild = self.get_guild(self.config['guild'])
        channel = guild.get_channel(self.log_channel)
        if len(content) >= 1900:
            fp = io.StringIO(content)
            file = nextcord.File(fp, f"{dt.datetime.now().isoformat()}.log")
            await channel.send(file=file)

        else:
            await channel.send("```" + content + "```")

    def log(self, message: str, level: str = "INFO", exc_info=None, *, print_to_console=False, send_to_discord=True):
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
        if send_to_discord:
            try:
                log_task = asyncio.create_task(self._log(message, level, exc_info=exc_info))
                self.background_tasks.add(log_task)
                log_task.add_done_callback(self.background_tasks.discard)
            except RuntimeError as e:
                self.error("Logging Error: No running event loop, you probably need to set send_to_discord=False",
                           exc_info=e, send_to_discord=False)

    async def on_error(self, event_method, *args, **kwargs):
        msg = f'Ignoring exception in {event_method}\n{traceback.format_exc()}'
        self.log(msg, "EXCEPTION")

    async def on_command_error(self, context, exception):
        trace = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        msg = f'Ignoring exception in command {context.command}:\n{trace}'
        self.log(msg, "EXCEPTION")

    async def on_interaction(self, i: Interaction):
        # await i.response.defer()
        close_old_connections()
        data = i.data
        user = i.user
        channel = i.channel
        guild = i.guild
        message = user.display_name + " #" + guild.name + "-" + channel.name + " Data:: "
        for key, value in data.items():
            message += " " + str(key) + ": " + str(value) + ","
        self.info(message + "\n", send_to_discord=False)
        await self.process_application_commands(i)

    async def on_application_command_error(self, i: nextcord.Interaction, exception: Exception):
        if isinstance(exception, ApplicationCheckFailure):
            await i.send("You do not have permission to use this command!", ephemeral=True)
            return
        else:
            await i.send("An error occurred! Please contact planning if this issue persists", ephemeral=True)
            trace = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
            msg = f'Ignoring exception in command {i.application_command}:\n{trace}'
            self.log(msg, "ERROR")

    fish = [
        1196466346481950720,
        1184940013331419287,
        1214014681987940452
    ]

    async def on_message(self, message):
        close_old_connections()
        if message.author.bot:
            return
        if "fish" in message.content.lower():
            if message.author.id == 666753178053902338:
                await message.reply("https://www.youtube.com/watch?v=whnZSnW3XsI")
            elif message.channel.id in self.fish:
                if "monica" in message.content.lower():
                    if randrange(2) == 1:
                        await message.reply("https://www.youtube.com/watch?v=whnZSnW3XsI")
                else:
                    if randrange(3) == 2:
                        await message.reply("https://www.youtube.com/watch?v=whnZSnW3XsI")

    def remove(self, id: int):
        user = DiscordUser.objects.filter(id=id).first()
        if user is None:
            return "User: " + str(id) + " left guild. Cannot find info in DB!"
        user.delete()
        return "User: " + str(id) + " left guild. Deleting records!"

    async def on_member_remove(self, member):
        self.info(await sync_to_async(self.remove)(member.id))

    def error(self, message, *, exc_info=None, **kwargs):
        self.log(message, "ERROR", exc_info=exc_info, **kwargs)

    def warning(self, message, *, exc_info=None, **kwargs):
        self.log(message, "WARNING", exc_info=exc_info, **kwargs)

    def info(self, message, *, exc_info=None, **kwargs):
        self.log(message, "INFO", exc_info=exc_info, **kwargs)

    def debug(self, message, *, exc_info=None, **kwargs):
        self.log(message, "DEBUG", exc_info=exc_info, **kwargs)
