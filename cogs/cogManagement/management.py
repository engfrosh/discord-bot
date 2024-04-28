"""Discord Management COG."""

import logging
from typing import Optional
# from typing import List
from nextcord.ext import commands
from nextcord import slash_command, Interaction, PermissionOverwrite, TextChannel, Role, Permissions
from nextcord import Attachment, Member
from asgiref.sync import sync_to_async
import time
from django.contrib.auth.models import Permission, Group

from common_models.models import RoleInvite, DiscordUser, FroshRole
from django.contrib.auth.models import User

from EngFroshBot import EngFroshBot, is_admin, has_permission, is_superadmin
import boto3
from botocore.exceptions import ClientError

import cogs.cogManagement.utils as utils

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

    @slash_command(name="spirit_on_duty", description="Sets the current spirit on duty.")
    @has_permission("common_models.spirit_on_duty")
    async def spirit_on_duty(self, i: Interaction, user1: Optional[Member] = None, user2: Optional[Member] = None,
                             user3: Optional[Member] = None, user4: Optional[Member] = None,
                             user5: Optional[Member] = None):
        role = i.guild.get_role(self.config['spirit_role'])
        for m in role.members:
            await m.remove_roles(role)
        if user1 is not None:
            await user1.add_roles(role)
        if user2 is not None:
            await user2.add_roles(role)
        if user3 is not None:
            await user3.add_roles(role)
        if user4 is not None:
            await user4.add_roles(role)
        if user5 is not None:
            await user5.add_roles(role)
        await i.send("Changed spirit on duty!", ephemeral=True)

    def get_all_non_kick(self):
        users = list(User.objects.filter(is_staff=False))
        planning = FroshRole.objects.filter(name="Planning").first().group
        head = FroshRole.objects.filter(name="Head").first().group
        exempt = Group.objects.get_or_create(name="Kick Exempt")[0]
        users = DiscordUser.objects.exclude(user__groups__in=[planning, head, exempt])
        discords = list()
        for user in users:
            discords += [user.id]
        return discords

    @slash_command(name="kick_all", description="Kicks all non planning users")
    @is_admin()
    async def kick_all(self, i: Interaction):
        await i.response.defer()
        non_planning = await sync_to_async(self.get_all_non_kick)()
        guild = i.guild
        for user in non_planning:
            try:
                await guild.get_member(user).kick(reason="Frosh is over!")
            except Exception:
                pass
        await i.send("Kicked all users!", ephemeral=True)

    @slash_command(name="add_role_to_role", description="Adds a role to every user with a role")
    @is_admin()
    async def add_role_to_role(self, i: Interaction, target_role: Role, add_role: Role):
        members = target_role.members
        for member in members:
            await member.add_roles(add_role)
        await i.send("Added role to all users with a role", ephemeral=True)

    @slash_command(name="add_pronoun", description="Adds a pronoun to a user")
    async def add_pronoun(self, i: Interaction, user: Member, emoji: str):
        try:
            await sync_to_async(utils.discord_add_pronoun)(emoji, user.id)
            new_name = await sync_to_async(utils.compute_discord_name)(user.id)
            await user.edit(nick=new_name)
        except Exception as e:
            self.bot.log("Failed to add pronoun to user " + user.name, level="ERROR")
            self.bot.log(e, level="ERROR")
            await i.send("Failed to add pronoun!", ephemeral=True)
            return
        await i.send("Added user pronoun!", ephemeral=True)

    @slash_command(name="remove_pronoun", description="Removes a pronoun from a user")
    async def remove_pronoun(self, i: Interaction, user: Member, emoji: str):
        try:
            await sync_to_async(utils.discord_remove_pronoun)(emoji, user.id)
            new_name = await sync_to_async(utils.compute_discord_name)(user.id)
            await user.edit(nick=new_name)
        except Exception as e:
            self.bot.log("Failed to remove pronoun from user " + user.name, level="ERROR")
            self.bot.log(e, level="ERROR")
            await i.send("Failed to remove pronoun!", ephemeral=True)
            return
        await i.send("Removed user pronoun!", ephemeral=True)

    def add_perm_sync(self, id, perm):
        disc_user = DiscordUser.objects.filter(id=id).first()
        if disc_user is None:
            return False
        user = disc_user.user
        perm = Permission.objects.filter(codename=perm).first()
        if perm is None:
            return False
        user.user_permissions.add(perm)
        return True

    @slash_command(name="add_perm", description="Adds a permission to a user")
    @is_admin()
    async def add_perm(self, i: Interaction, user: Member, perm: str):
        status = await sync_to_async(self.add_perm_sync)(user.id, perm)
        if status:
            await i.send("Added permission", ephemeral=True)
        else:
            await i.send("Failed to add permission", ephemeral=True)

    def add_perm_group_sync(self, group, perm):
        g = Group.objects.get(name=group)
        if g is None:
            return False
        perm = Permission.objects.filter(codename=perm).first()
        if perm is None:
            return False
        g.permissions.add(perm)
        return True

    @slash_command(name="add_group_perm", description="Adds a permission to a group")
    @is_admin()
    async def add_group_perm(self, i: Interaction, group: str, perm: str):
        status = await sync_to_async(self.add_perm_group_sync)(group, perm)
        if status:
            await i.send("Added permission", ephemeral=True)
        else:
            await i.send("Failed to add permission", ephemeral=True)

    def add_group_sync(self, ids, group):
        g = Group.objects.get(name=group)
        if g is None:
            return False
        for id in ids:
            disc_user = DiscordUser.objects.filter(id=id).first()
            if disc_user is None:
                continue
            user = disc_user.user
            g.user_set.add(user)
        return True

    @slash_command(name="add_group", description="Adds a group to all users in a role or a specific user")
    @is_admin()
    async def add_group(self, i: Interaction, users: Role, group: str):
        ids = []
        for member in users.members:
            ids += [member.id]
        status = await sync_to_async(self.add_group_sync)(ids, group)
        if status:
            await i.send("Added group", ephemeral=True)
        else:
            await i.send("Failed to add group", ephemeral=True)

    @slash_command(name="change_nick", description="Changed a user's nickname. Warning: Disables pronouns")
    @is_admin()
    async def change_nick(self, i: Interaction, user: Member, name: str):
        result = await sync_to_async(utils.discord_override_name)(user.id, name)
        if not result:
            await i.send("Failed to change name!", ephemeral=True)
            return
        await user.edit(nick=name)
        await i.send("Changed nickname!", ephemeral=True)

    @slash_command(name="clear_nick", description="Resets a user's nickname to the BOT's default")
    @is_admin()
    async def clear_nick(self, i: Interaction, user: Member):
        result = await sync_to_async(utils.discord_clear_name)(user.id)
        if not result:
            await i.send("Failed to clear name!", ephemeral=True)
            return
        new_name = await sync_to_async(utils.compute_discord_name)(user.id)
        await user.edit(nick=new_name)

        await i.send("Cleared nickname!", ephemeral=True)

    @slash_command(name="clear_nicks", description="Clears all nicknames")
    async def clear_nicks(self, i: Interaction):
        async for user in i.guild.fetch_members():
            try:
                await sync_to_async(utils.discord_clear_name)(user.id)
                new_name = await sync_to_async(utils.compute_discord_name)(user.id)
                await user.edit(nick=new_name)
            except Exception:
                pass
        await i.send("Cleared nicknames!", ephemeral=True)

    @slash_command(name="echo", description="Echos messages back from the bot")
    @is_admin()
    async def echo(self, i: Interaction, message: str):
        await i.send("Echod message!", ephemeral=True)
        await i.channel.send(message)

    @slash_command(name="channels", description="Lists all the channels in the server")
    @is_admin()
    async def categories(self, i: Interaction):
        response = ""
        for category in i.guild.categories:
            name = category.name
            id = category.id
            response += name + " - " + str(id) + "\nText channels:\n"
            text_channels = category.text_channels
            for channel in text_channels:
                response += "\t" + channel.name + " - " + str(channel.id) + "\n"
            response += "Voice channels:\n"
            voice_channels = category.voice_channels
            for channel in voice_channels:
                response += "\t" + channel.name + " - " + str(channel.id) + "\n"
            response += "\n"
        # Stolen from https://stackoverflow.com/a/13673133
        chunks, chunk_size = len(response), 1950
        chunk_list = [response[i:i+chunk_size] for i in range(0, chunks, chunk_size)]
        for c in chunk_list:
            await i.send("```" + c + "```", ephemeral=True)

    @slash_command(name="overwrites", description="Lists the overwrites on a channel")
    @is_admin()
    async def overwrites(self, i: Interaction, id):
        channels = i.guild.text_channels
        channel = None
        for c in channels:
            if c.id == int(id):
                channel = c
                break
        if channel is None:
            channels = i.guild.voice_channels
            for c in channels:
                if c.id == int(id):
                    channel = c
                    break
        if channel is None:
            await i.send("Cannot find channel!", ephemeral=True)
            return
        overwrites = channel.overwrites
        response = "Overwrites:\n"
        for role, perms in overwrites.items():
            tup = perms.pair()
            view = not tup[1].read_messages
            send = not tup[1].send_messages
            response += role.name + " - View: " + str(view) + " - Send: " + str(send) + "\n" + \
                str(tup[1]) + "\n" + str(tup[0]) + "\n"
        await i.send(response, ephemeral=True)

    @slash_command(name="add_overwrite", description="Adds an overwrite for a channel")
    @is_admin()
    async def add_overwrite(self, i: Interaction, id, role: Role, name, value):
        channels = i.guild.text_channels
        channel = None
        for c in channels:
            if c.id == int(id):
                channel = c
                break
        if channel is None:
            channels = i.guild.voice_channels
            for c in channels:
                if c.id == int(id):
                    channel = c
                    break
        if channel is None:
            await i.send("Cannot find channel!", ephemeral=True)
            return
        # This is magic dictionary unpacking from https://stackoverflow.com/a/22384521
        await channel.set_permissions(role, **{name: bool(value)})
        await i.send("Successfully changed overwrites!", ephemeral=True)

    @slash_command(name="rename", description="Renames a channel")
    @is_admin()
    async def rename(self, i: Interaction, id, name):
        channels = i.guild.text_channels
        channel = None
        for c in channels:
            if c.id == int(id):
                channel = c
                break
        if channel is None:
            channels = i.guild.voice_channels
            for c in channels:
                if c.id == int(id):
                    channel = c
                    break
        if channel is None:
            await i.send("Cannot find channel!", ephemeral=True)
            return
        # This is magic dictionary unpacking from https://stackoverflow.com/a/22384521
        await channel.edit(name=name)
        await i.send("Successfully renamed channel!", ephemeral=True)

    @slash_command(name="deleteoverwrite", description="Deletes an overwrite for a channel")
    @is_admin()
    async def delete_overwrite(self, i: Interaction, id, role: Role):
        channels = i.guild.text_channels
        channel = None
        for c in channels:
            if c.id == int(id):
                channel = c
                break
        if channel is None:
            channels = i.guild.voice_channels
            for c in channels:
                if c.id == int(id):
                    channel = c
                    break
        if channel is None:
            await i.send("Cannot find channel!", ephemeral=True)
            return
        await channel.set_permissions(role, overwrite=None)
        await i.send("Successfully changed overwrites!", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        invites = await guild.invites()
        role_invites = RoleInvite.objects.all()
        for i in invites:
            role_invite = await sync_to_async(role_invites.filter(link=i.id).first)()
            if i.uses == 1 and role_invite is not None:
                await i.delete()
                for role in role_invite.role.split(","):
                    await member.add_roles(guild.get_role(int(role.strip())))
                await sync_to_async(utils.link_userdetails)(role_invite,
                                                            member.id, member.name, member.discriminator)
                name = await sync_to_async(utils.compute_discord_name)(member.id)
                await member.edit(nick=name)
                await sync_to_async(role_invite.delete)()
                break

    @slash_command(name="create_invite", description="Creates an invite that automatically grants a role.")
    @has_permission("common_models.create_invite")
    async def create_invite(self, i: Interaction, role: Role, name: str):
        channel = i.guild.system_channel
        if channel is None:
            await i.send("Error: System channel is not configured!", ephemeral=True)
            return
        invite = await channel.create_invite(max_uses=2)
        role_invite = RoleInvite()
        role_invite.link = invite.id
        role_invite.role = str(role.id)
        role_invite.nick = ""
        role_invite.user = await sync_to_async(utils.create_user)(name)

        await sync_to_async(role_invite.save)()
        await i.send(invite.url, ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """On raw reaction add handling."""

        emoji = payload.emoji
        user_id = payload.user_id
        member = payload.member
        message_id = payload.message_id

        if user_id == self.bot.user.id:
            return
        for message in await sync_to_async(utils.get_messages)("pronoun"):
            if message_id == message.id:
                try:
                    await sync_to_async(utils.discord_add_pronoun)(emoji.name, user_id)
                    new_name = await sync_to_async(utils.compute_discord_name)(user_id)
                    if len(new_name) > 32:
                        self.bot.info("Did not add pronoun to user (name too long)" +
                                      member.name + " -> " + new_name, send_to_discord=False)
                    else:
                        await member.edit(nick=new_name)
                        self.bot.info("Added pronoun to user " + member.name + " -> " + new_name, send_to_discord=False)
                    break
                except Exception as e:
                    self.bot.log("Failed to add pronoun to user " + member.name, level="ERROR",)
                    self.bot.log(e, level="ERROR")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """On raw reaction remove handling."""

        emoji = payload.emoji
        user_id = payload.user_id
        guild = self.bot.get_guild(self.bot.config['guild'])
        member = guild.get_member(user_id)
        message_id = payload.message_id

        if user_id == self.bot.user.id:
            return
        for message in await sync_to_async(utils.get_messages)("pronoun"):
            if message_id == message.id:
                try:
                    await sync_to_async(utils.discord_remove_pronoun)(emoji.name, user_id)
                    new_name = await sync_to_async(utils.compute_discord_name)(user_id)
                    await member.edit(nick=new_name)
                    self.bot.info("Removed pronoun from user " + member.name + " -> " + new_name, send_to_discord=False)
                    break
                except Exception as e:
                    self.bot.log("Failed to remove pronoun from user " + member.name, level="ERROR")
                    self.bot.log(e, level="ERROR")

    @slash_command(name="pronoun_create", description="Creates a pronoun option")
    @is_admin()
    async def pronoun_create(self, i: Interaction, name: str, emote: str):
        await sync_to_async(utils.create_pronoun)(name, emote)
        await i.send("Successfully created pronoun", ephemeral=True)

    @slash_command(name="send_pronoun_message",
                   description="Sends a message to this channel for users to select their pronouns")
    @is_admin()
    async def send_pronoun_message(self, i: Interaction):
        """Send pronoun message in this channel."""

        await i.response.defer(with_message=True, ephemeral=True)
        text = await sync_to_async(utils.create_discord_pronoun_message)()
        message = await i.channel.send(text)

        for emote in await sync_to_async(utils.get_pronoun_emotes)():
            await message.add_reaction(emote)
        await sync_to_async(utils.register_message)("pronoun", message.id)

        await i.send("Successfully created message!", ephemeral=True)
        return

    @slash_command(name="create_user", description="Creates a user")
    @is_admin()
    async def create_user(self, i: Interaction, user: Member, first_name: str, last_name: str):
        await sync_to_async(utils.create_discord_user)(first_name, last_name, user.id,
                                                       user.name, user.discriminator)
        await i.send("Created user in DB!", ephemeral=True)

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

    @slash_command(name="create_backend_group", description="Creates a group in the backend Django system")
    @is_admin()
    async def create_backend_group(self, i: Interaction, name: str):
        await sync_to_async(Group.objects.create)(name=name)
        await i.send("Created backend group!", ephemeral=True)

    @slash_command(name="create_group", description="Creates a channel with several roles allowed in it")
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

    @slash_command(name="rename_all", description="Renames all users in the discord server")
    @is_admin()
    async def rename_all(self, i: Interaction):
        await i.response.defer(with_message=True, ephemeral=True)
        for m in i.guild.members:
            name = await sync_to_async(utils.compute_discord_name)(m.id)
            if m.display_name != name:
                try:
                    await m.edit(nick=name)
                except Exception as e:
                    logger.error(e)
        await i.send("Reset all users nicks", ephemeral=True)

    @slash_command(name="create_channel",
                   description="Creates a channel with two roles allowed in it but only named with the first group")
    @has_permission("common_models.create_channel")
    async def create_channel(self, i: Interaction, category: str, name: str, roles: str):
        roles = roles.split()
        guild = i.guild
        if len(roles) < 1:
            await i.send("You must specify at least 1 role!", ephemeral=True)
            return

        category = self.get(guild.categories, category)
        if category is None:
            await i.send("Unable to find a category with that name!", ephemeral=True)
            return
        r = []
        for j in range(len(roles)):
            r += [self.get(guild.roles, roles[j].title())]
            if r[j] is None:
                await i.send("Unable to find a role with the name \""+roles[j]+"\"!", ephemeral=True)
                return
        if self.get(category.text_channels, name) is not None:
            await i.send("This channel already exists!", ephemeral=True)
            return
        overwrites = {guild.default_role: PermissionOverwrite(view_channel=False)}
        for role in r:
            overwrites[role] = PermissionOverwrite(view_channel=True)
        await guild.create_text_channel(name, category=category, overwrites=overwrites)

        await i.send("Successfully created channel!", ephemeral=True)
        return

    DEFAULT_MAGIC_LINK_EMAIL_TEXT = \
        """Welcome to EngFrosh, Head's Discord!
    Here is your magic link to log into the Discord server: {link}
    You will receive more information from your group co shortly.
    If you need any help or any questions, please email directors@engfrosh.com"""

    DEFAULT_MAGIC_LINK_EMAIL_HTML = \
        """<html lang='en'>
            <body>
                <h1>Welcome to EngFrosh, Head's Discord!</h1><br/>
                <p><a href='{link}' >Here</a> is your magic link to log into the Discord server.</p>
                <br/>
                <p>You will receive more information from your group co shortly.</p>
                <br/>
                <p>If you need any help or any questions,
                please email <a href="mailto:directors@engfrosh.com">directorss@engfrosh.com</a>
                <br/>
                <br/>
                {link}
                </p>
            </body>
        </html>
        """
    # Note, google tends to get rid of some link elements.
    DEFAULT_MAGIC_LINK_EMAIL_SUBJECT = "Welcome to EngFrosh Heads Discord!"
    SENDER_EMAIL = "noreply@engfrosh.com"

    @slash_command(name="import_users")
    @is_admin()
    async def import_users(self, i: Interaction, csv_file: Attachment):
        await i.response.defer(with_message=True, ephemeral=True)
        data = await csv_file.read()
        data = data.decode("UTF-8").split('\n')
        AWS_REGION = "us-east-2"

        # The character encoding for the email.
        CHARSET = "UTF-8"

        # Create a new SES resource and specify a region.
        client = boto3.client('ses', region_name=AWS_REGION)
        rows = []

        for row in data:
            if row == "":
                continue
            split = row.split(',')
            name = split[0]
            role = split[1]
            email = split[2]
            role = self.get(i.guild.roles, role.title())
            if role is None:
                await i.send("Error: Invalid role!", ephemeral=True)
                return
            channel = i.guild.system_channel
            if channel is None:
                await i.send("Error: System channel is not configured!", ephemeral=True)
                return
            split[1] = role
            rows += [split]
        for row in rows:
            name = row[0]
            role = row[1]
            email = row[2]
            invite = await channel.create_invite(max_uses=2)
            role_invite = RoleInvite()
            role_invite.link = invite.id
            role_invite.role = str(role.id)
            role_invite.nick = name
            await sync_to_async(role_invite.save)()
            url = invite.url
            try:
                client.send_email(
                    Destination={
                        'ToAddresses': [
                            email,
                        ],
                    },
                    Message={
                        'Body': {
                            'Html': {
                                'Charset': CHARSET,
                                'Data': self.DEFAULT_MAGIC_LINK_EMAIL_HTML.format(link=url),
                            },
                            'Text': {
                                'Charset': CHARSET,
                                'Data': self.DEFAULT_MAGIC_LINK_EMAIL_TEXT.format(link=url),
                            },
                        },
                        'Subject': {
                            'Charset': CHARSET,
                            'Data': self.DEFAULT_MAGIC_LINK_EMAIL_SUBJECT,
                        },
                    },
                    Source=self.SENDER_EMAIL
                )
                time.sleep(0.1)
            except ClientError as e:
                await i.send(e.response['Error']['Message'], ephemeral=True)
        await i.send("Sent emails!", ephemeral=True)


def setup(bot):
    """Management COG setup."""
    bot.add_cog(Management(bot))
