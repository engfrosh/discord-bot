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

    # @slash_command(name="purge", description="Purge all messages from this channel.")
    # async def slash_purge_channel(self, interaction: Interaction):
    #     # TODO add check that user is allowed to purge

    #     if isinstance(interaction.channel, nextcord.TextChannel):
    #         await interaction.response.defer(ephemeral=True, with_message=True)
    #         await interaction.channel.purge()
    #         interaction.followup.edit_message(interaction.response.)
    #         await interaction.response.edit_message(content="Channel Purged")
    #     else:
    #         await interaction.response.send_message("Sorry, cannot purge this channel.", ephemeral=True)


def setup(bot):
    bot.add_cog(Management(bot))
