"""Management COG."""

from __future__ import annotations

import logging

from nextcord.ext import commands
from nextcord import slash_command, Interaction
import nextcord


logger = logging.getLogger("cog.management")


class Management(commands.Cog):
    """Management Cog"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @slash_command(name="purge", description="Purge all messages from this channel.", dm_permission=False,
                   default_member_permissions=8)
    async def slash_purge_channel(self, interaction: Interaction):

        if isinstance(interaction.channel, nextcord.TextChannel):
            await interaction.response.defer(ephemeral=True, with_message=True)
            await interaction.channel.purge()
            await interaction.send(content="Channel Purged", ephemeral=True)
        else:
            await interaction.response.send_message("Sorry, cannot purge this channel.", ephemeral=True)


def setup(bot):
    bot.add_cog(Management(bot))
