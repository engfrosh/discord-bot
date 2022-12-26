"""Discord Management COG."""

import logging
import os
from typing import Optional
# from typing import List
from nextcord.ext import commands, application_checks
from nextcord import slash_command, Interaction, PermissionOverwrite, TextChannel, File
from nextcord.utils import get
import random

from common_models.models import DiscordVirtualTeam

from EngFroshBot import EngFroshBot

SOOPP_BINGO_PATH = "offline-files/soopp-bingo"

logger = logging.getLogger("CogManagement")

admin_role = EngFroshBot.instance.admin_role


class Management(commands.Cog):
    """Discord Management Cog"""

    def __init__(self, bot: EngFroshBot) -> None:
        """Management COG init"""
        self.bot = bot
        self.config = bot.config["module_settings"]["management"]
        self.load_bingo_cards()

    def load_bingo_cards(self) -> None:
        """Load all the bingo cards in the folder."""
        self.bingo_cards = [
            SOOPP_BINGO_PATH + "/" + f for f in os.listdir(SOOPP_BINGO_PATH)
            if os.path.isfile(os.path.join(SOOPP_BINGO_PATH, f))]

    @slash_command(name="purge", description="Purge all messages from this channel.",
                   dm_permission=False, default_member_permissions=8)
    @application_checks.has_role(admin_role)
    async def purge(self, i: Interaction, channel_id: Optional[str] = None):
        """Purge the channel, only available to admin."""

        if isinstance(i.channel, TextChannel):
            await i.channel.purge()  # type: ignore
        else:
            await i.send("Cannot purge this channel type.", ephemeral=True)

        return

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """On raw reaction add handling."""

        channel_id = payload.channel_id
        emoji = payload.emoji
        user_id = payload.user_id
        member = payload.member
        reaction_type = payload.event_type
        message_id = payload.message_id

        if user_id == self.bot.user.id:
            return

        if message_id in self.config["pronoun_message"]:
            guild = self.bot.get_guild(self.bot.config["guild"])
            if not guild:
                await self.bot.error(f"Could not get guild {self.bot.config['guild']}")
                return
            if emoji.name == "1️⃣":
                role = guild.get_role(self.config["pronouns"]["he"])
                await member.add_roles(role)
            elif emoji.name == "2️⃣":
                role = guild.get_role(self.config["pronouns"]["she"])
                await member.add_roles(role)
            elif emoji.name == "3️⃣":
                role = guild.get_role(self.config["pronouns"]["they"])
                await member.add_roles(role)
            elif emoji.name == "4️⃣":
                role = guild.get_role(self.config["pronouns"]["ask"])
                await member.add_roles(role)
            else:
                await self.bot.log(
                    f"Channel: {channel_id} Emoji: {emoji} user_id: {user_id} reaction_type: {reaction_type}")
                return

        elif message_id in self.config["bingo_message"]:
            has_card = await self.bot.db_int.check_user_has_bingo_card(user_id)
            if has_card:
                await member.send("You already have a bingo card!")
                return

            i = random.randint(0, len(self.bingo_cards) - 1)
            tries = 0
            while True:
                tries += 1
                if tries > len(self.bingo_cards):
                    await self.bot.error("No bingo cards remaining.")
                    return

                card = self.bingo_cards[i]
                # All the card names must be integers.
                card_num = int(os.path.splitext(os.path.basename(card))[0])

                linked = await self.bot.db_int.check_bingo_card_used(card_num)
                if not linked:
                    break
                else:
                    i += 1
                    if i >= len(self.bingo_cards):
                        i = 0

            await self.bot.db_int.add_bingo_card(card_num, user_id)

            await member.send("Here is you SOOPP bingo card!", file=File(card, "SOOPP Bingo Card.pdf"))
            logger.info(f"Sent bingo card {card} to user {user_id}")

            return

        elif message_id in self.config["virtual_team_message"]:
            virtual_teams = await self.bot.db_int.get_all_virtual_teams()
            virtual_team_ids = [vt.role_id for vt in virtual_teams]
            if any([role.id in virtual_team_ids for role in member.roles]):
                await member.send("You are already part of a virtual team!")
                return

            guild = self.bot.get_guild(self.bot.config["guild"])
            if not guild:
                await self.bot.error("Could not get guild.")
                return

            allowed_teams = []
            for vt in virtual_teams:
                if vt.num_member < self.config["num_members_per_team"]:
                    allowed_teams.append(vt)

            num_added = 0
            while len(allowed_teams) < 2:
                team_name = f"VTeam {len(virtual_teams) + 1 + num_added}"
                new_role = await guild.create_role(name=team_name)
                await self.bot.db_int.create_virtual_team(new_role.id)
                allowed_teams.append(DiscordVirtualTeam(new_role.id, 0))
                num_added += 1

            role = guild.get_role(random.choice(allowed_teams).role_id)
            await member.add_roles(role)

            await self.bot.db_int.increment_virtual_team_count(role.id)
            await member.send(f"You've been added to virtual team {role.name}")

            return

        return

    @slash_command(name="pronoun_message",
                   description="Sends a message to this channel for users to select their pronouns",
                   dm_permission=False, default_member_permissions=8)
    @application_checks.has_role(admin_role)
    async def send_pronoun_message(self, i: Interaction):
        """Send pronoun message in this channel."""

        message = await i.channel.send(
            "Select your pronouns:\n:one: He/Him\n:two: She/Her\n:three: They/Them\n:four: Ask Me")

        await message.add_reaction("1️⃣")
        await message.add_reaction("2️⃣")
        await message.add_reaction("3️⃣")
        await message.add_reaction("4️⃣")
        await i.send("Successfully created message!", ephemeral=True)
        return

    @slash_command(name="bingo_message",
                   description="Sends a message to this channel for users to play bingo",
                   dm_permission=False, default_member_permissions=8)
    @application_checks.has_role(admin_role)
    async def send_bingo_message(self, i: Interaction):
        """Send bingo message in this channel."""

        message = await i.channel.send("React to this message to get a SOOPP Bingo Card.")

        await message.add_reaction("🤚")
        await i.send("Successfully created message!", ephemeral=True)

        return

    @slash_command(name="virtual_team_message",
                   description="Sends a message to this channel for users to join virtual teams",
                   dm_permission=False, default_member_permissions=8)
    @application_checks.has_role(admin_role)
    async def send_virtual_team_message(self, i: Interaction):
        """Send virtual team message in this channel."""

        message = await i.channel.send("React to this message to join a virtual team.")

        await message.add_reaction("🤚")
        await i.send("Successfully created message!", ephemeral=True)

        return

    @slash_command(name="get_overwrites",
                   description="Gets the permission overwrites for the current channel",
                   dm_permission=False, default_member_permissions=8)
    @application_checks.has_role(admin_role)
    async def get_overwrites(self, i: Interaction, channel_id: Optional[int] = None):
        """Get all the permission overwrites for the current channel."""

        if i.user.id not in self.config["superadmin"]:  # type: ignore
            return

        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                overwrites = channel.overwrites
            else:
                await i.send("error", ephemeral=True)
                return

        else:

            overwrites = i.channel.overwrites  # type: ignore

        msg = "```\n"
        for k, v in overwrites.items():
            msg += f"{k} {k.id}:\n"
            for p in v:
                if p[1] is not None:
                    msg += f"    {p}\n"
        msg += "```"

        await i.send(msg, ephemeral=True)
        return

    @slash_command(name="shutdown",
                   description="Shuts off the discord bot",
                   dm_permission=False, default_member_permissions=8)
    @application_checks.has_role(admin_role)
    async def shutdown(self, i):
        """Shuts down and logs out the discord bot."""
        if i.user.id in self.config["superadmin"]:
            await i.send("Logging out.", ephemeral=True)
            await self.bot.log("Logging out.")
            await self.bot.logout()
            exit()

        else:
            return

    @slash_command(name="create_role", description="Creates a roles and it's channels")
    async def create_role(self, i: Interaction, name: str):
        guild = i.guild
        role = await guild.create_role(name=name, mentionable=True, hoist=True)
        overwrites = {role: PermissionOverwrite(view_channel=True),
                      guild.default_role: PermissionOverwrite(view_channel=False)}
        category = await guild.create_category(name=name, overwrites=overwrites)
        await guild.create_text_channel(name=name, category=category)
        await i.send("Successfully created role and channels!", ephemeral=True)
        return

    @slash_command(name="create_group", description="Creates a channel with two roles allowed in it")
    async def create_group(self, i: Interaction, role1: str, role2: str):
        guild = i.guild
        category = get(guild.categories, name=role1)
        overwrites = {get(guild.roles, name=role2): PermissionOverwrite(view_channel=True),
                      get(guild.roles, name=role1): PermissionOverwrite(view_channel=True),
                      guild.default_role: PermissionOverwrite(view_channel=False)}
        await guild.create_text_channel(role1 + "-" + role2, category=category, overwrites=overwrites)

        await i.send("Successfully created channel!", ephemeral=True)
        return


def setup(bot):
    """Management COG setup."""
    bot.add_cog(Management(bot))
