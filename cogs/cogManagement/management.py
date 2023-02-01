"""Discord Management COG."""

import logging
from typing import Optional
# from typing import List
from nextcord.ext import commands
from nextcord import slash_command, Interaction, PermissionOverwrite, TextChannel, Role, Permissions, SlashOption
import random
from asgiref.sync import sync_to_async

from common_models.models import VirtualTeam, RoleInvite

from EngFroshBot import EngFroshBot, is_admin, has_permission, is_superadmin

logger = logging.getLogger("CogManagement")


class Management(commands.Cog):
    """Discord Management Cog"""

    def __init__(self, bot: EngFroshBot) -> None:
        """Management COG init"""
        self.bot = bot
        self.config = bot.config["module_settings"]["management"]

    @slash_command(name="purge", description="Purge all messages from this channel.")
    @has_permission("common_models.purge_channels")
    async def purge(self, i: Interaction, channel_id: Optional[str] = None):
        """Purge the channel, only available to admin."""

        if isinstance(i.channel, TextChannel):
            await i.channel.purge()  # type: ignore
            await i.send("Successfully purged channel!", ephemeral=True)
        else:
            await i.send("Cannot purge this channel type.", ephemeral=True)

        return

    @slash_command(name="echo", description="Echos messages back from the bot")
    @is_admin()
    async def echo(self, i: Interaction, message: str):
        await i.send("Echod message!", ephemeral=True)
        await i.channel.send(message)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        invites = await guild.invites()
        role_invites = RoleInvite.objects.all()
        for i in invites:
            role_invite = await sync_to_async(role_invites.filter(link=i.id).first)()
            if i.uses == 1 and role_invite is not None:
                await member.add_roles(guild.get_role(role_invite.role))
                await member.edit(nick=role_invite.nick)
                await sync_to_async(role_invite.delete)()
                await i.delete()
                break

    @slash_command(name="create_invite", description="Creates an invite that automatically grants a role.")
    @has_permission("common_models.create_invite")
    async def create_invite(self, i: Interaction, role: Role, nick: Optional[str] = SlashOption(required=False)):
        channel = i.guild.system_channel
        if channel is None:
            await i.send("Error: System channel is not configured!", ephemeral=True)
            return
        invite = await channel.create_invite(max_uses=2)
        role_invite = RoleInvite()
        role_invite.link = invite.id
        role_invite.role = role.id
        role_invite.nick = nick
        await sync_to_async(role_invite.save)()
        await i.send(invite.url, ephemeral=True)

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
                allowed_teams.append(VirtualTeam(new_role.id, 0))
                num_added += 1

            role = guild.get_role(random.choice(allowed_teams).role_id)
            await member.add_roles(role)

            await self.bot.db_int.increment_virtual_team_count(role.id)
            await member.send(f"You've been added to virtual team {role.name}")

            return

        return

    @slash_command(name="pronoun_message",
                   description="Sends a message to this channel for users to select their pronouns")
    @is_admin()
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

    @slash_command(name="virtual_team_message",
                   description="Sends a message to this channel for users to join virtual teams")
    @is_admin()
    async def send_virtual_team_message(self, i: Interaction):
        """Send virtual team message in this channel."""

        message = await i.channel.send("React to this message to join a virtual team.")

        await message.add_reaction("🤚")
        await i.send("Successfully created message!", ephemeral=True)

        return

    @slash_command(name="get_overwrites",
                   description="Gets the permission overwrites for the current channel")
    @is_admin()
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
                   description="Shuts off the discord bot")
    @is_superadmin()
    async def shutdown(self, i):
        """Shuts down and logs out the discord bot."""
        if i.user.id in self.config["superadmin"]:
            await i.send("Logging out.", ephemeral=True)
            await self.bot.log("Logging out.")
            await self.bot.logout()
            exit()

        else:
            return

    def get(self, data: list, name: str):
        name = name.lower()
        for d in data:
            if d.name.lower() == name:
                return d
        return None

    @slash_command(name="create_role", description="Creates a roles and it's channels")
    @has_permission("common_models.create_role")
    async def create_role(self, i: Interaction, name: str):
        guild = i.guild
        name = name.title()
        if self.get(guild.roles, name) is not None:
            await i.send("This role already exists!", ephemeral=True)
            return
        if self.get(guild.categories, name) is not None:
            await i.send("This category already exists!", ephemeral=True)
            return
        perms = Permissions(change_nickname=True, read_messages=True, send_messages=True)
        role = await guild.create_role(name=name, mentionable=True, hoist=True, permissions=perms)
        overwrites = {role: PermissionOverwrite(view_channel=True),
                      guild.default_role: PermissionOverwrite(view_channel=False)}
        category = await guild.create_category(name=name, overwrites=overwrites)
        await guild.create_text_channel(name=name.lower(), category=category)
        await i.send("Successfully created role and channels!", ephemeral=True)
        return

    @slash_command(name="create_group", description="Creates a channel with two roles allowed in it")
    @has_permission("common_models.create_channel")
    async def create_group(self, i: Interaction, roles: str):
        roles = roles.split()
        guild = i.guild
        if len(roles) < 1:
            await i.send("You must specify at least 1 role!", ephemeral=True)
            return
        role1 = roles[0].title()

        category = self.get(guild.categories, role1)
        if category is None:
            await i.send("Unable to find a category with that name!", ephemeral=True)
            return
        r = []
        for j in range(len(roles)):
            r += [self.get(guild.roles, roles[j].title())]
            if r[j] is None:
                await i.send("Unable to find a role with the name \""+roles[j]+"\"!", ephemeral=True)
                return
        name = roles[0].lower()
        for j in range(1, len(roles)):
            name += "-" + roles[j].lower()
        if self.get(category.text_channels, name) is not None:
            await i.send("This channel already exists!", ephemeral=True)
            return
        overwrites = {guild.default_role: PermissionOverwrite(view_channel=False)}
        for role in r:
            overwrites[role] = PermissionOverwrite(view_channel=True)
        await guild.create_text_channel(name, category=category, overwrites=overwrites)

        await i.send("Successfully created channel!", ephemeral=True)
        return

    @slash_command(name="create_channel", description="Creates a channel with two roles allowed in it but only named with the first group")
    @has_permission("common_models.create_channel")
    async def create_channel(self, i: Interaction, cat: str, roles: str):
        roles = roles.split()
        guild = i.guild
        if len(roles) < 1:
            await i.send("You must specify at least 1 role!", ephemeral=True)
            return
        role1 = roles[0].title()

        category = self.get(guild.categories, cat)
        if category is None:
            await i.send("Unable to find a category with that name!", ephemeral=True)
            return
        r = []
        for j in range(len(roles)):
            r += [self.get(guild.roles, roles[j].title())]
            if r[j] is None:
                await i.send("Unable to find a role with the name \""+roles[j]+"\"!", ephemeral=True)
                return
        name = roles[0].lower()
        if self.get(category.text_channels, name) is not None:
            await i.send("This channel already exists!", ephemeral=True)
            return
        overwrites = {guild.default_role: PermissionOverwrite(view_channel=False)}
        for role in r:
            overwrites[role] = PermissionOverwrite(view_channel=True)
        await guild.create_text_channel(name, category=category, overwrites=overwrites)

        await i.send("Successfully created channel!", ephemeral=True)
        return

def setup(bot):
    """Management COG setup."""
    bot.add_cog(Management(bot))
