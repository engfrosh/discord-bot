# region Imports
import logging

import nextcord
from nextcord.ext import commands
from nextcord import slash_command, Interaction, Member, SlashOption, TextChannel, NotFound, Role
from nextcord.ui import View, Button
from typing import Optional

from common_models.models import BooleanSetting, VerificationPhoto, Team, UserDetails, DiscordUser, FroshRole
from common_models.models import Puzzle, TeamPuzzleActivity, PuzzleGuess, DiscordRole

from django.core.files import File

from EngFroshBot import EngFroshBot, has_permission
from asgiref.sync import sync_to_async
import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse
import os
import json
import uuid
# endregion


logger = logging.getLogger("Cogs.Scav")


class VerifyButton(Button):
    def __init__(self, label: str, callback, photo: VerificationPhoto, channel: TextChannel):
        self.callback_fun = callback
        self.photo = photo
        self.channel = channel
        super().__init__(label=label)

    async def callback(self, i: Interaction):
        await self.callback_fun(i, self.photo, self.channel)


class Scav(commands.Cog):
    def __init__(self, bot: EngFroshBot):
        self.bot = bot
        self.server = bot.config["server"]
        self.config = bot.config["module_settings"]["scav"]

    def check_scavenger_setting_enabled(self):
        return BooleanSetting.objects.filter(id="SCAVENGER_ENABLED").first()

    async def scav_enabled(self):
        return await sync_to_async(self.check_scavenger_setting_enabled)()

    class ScavNotEnabledError(Exception):
        """Exception raised when scav is not enabled."""

    class TeamNotFoundError(Exception):
        """Exception raised when a team for the given information is not found."""

    class TeamAlreadyFinishedError(Exception):
        """Exception raised when a team is already finished scav."""

    def get_all_scav_teams(self):
        return list(Team.objects.filter(scavenger_enabled_for_team=True))

    async def update_scoreboard(self):
        """Update the scoreboard channel with the current standings."""

        logger.debug("Updating Scav board...")
        teams = await sync_to_async(self.get_all_scav_teams())()
        teams.sort(key=lambda team: team.current_question, reverse=True)

        msg = "```\n"

        cur_place = 0
        cur_question = None
        next_place = 1

        for team in teams:
            if team.current_question == cur_question:
                place = cur_place
                next_place += 1
            else:
                place = next_place
                cur_place = next_place
                next_place += 1
                cur_question = team.current_question

            msg += f"{place}. {team.display_name}: {team.current_question}\n"

        msg += "```"

        channels = self.config["scoreboard_channels"]

        await self.bot.send_to_all(msg, channels, purge_first=True)

    def get_user_from_discord(self, author: Member):
        user = DiscordUser.objects.filter(discord_username=author.name, discriminator=author.discriminator).first()
        if user is None:
            return None
        return UserDetails.objects.filter(user=user.user).first()

    def get_user_team(self, user: UserDetails):
        frosh_groups = FroshRole.objects.all()
        names = []
        for g in frosh_groups:
            names += [g.name]
        team = user.user.groups.exclude(name__in=names).first()
        if team is None:
            return None
        return Team.objects.filter(group=team).first()

    def get_user_role(self, user: UserDetails):
        frosh_groups = FroshRole.objects.all()
        names = []
        for g in frosh_groups:
            names += [g.name]
        role = user.user.groups.filter(name__in=names).first()
        if role is None:
            return None
        return role.name

    def team_scav_enabled(self, team: Team) -> bool:
        # This has to be here because team.scavenger_enabled has the property decorator
        return team.scavenger_enabled

    async def scav_user_allowed(self, i: Interaction) -> bool:
        """
        Check if the user and channel are correct and allowed to guess / request a hint,
        and send messages stating errors if not.

        """

        if i.channel.id not in self.config['team_channels']:
            await i.send("There is no scav team associated with this channel.", ephemeral=True)
            return False

        # Check that scav is enabled
        enabled = await self.scav_enabled()
        if not enabled:
            await i.send("Scav is not currently enabled.", ephemeral=True)
            return False
        user = await sync_to_async(self.get_user_from_discord)(i.user)
        team = await sync_to_async(self.get_user_team)(user)
        role = await sync_to_async(self.get_user_role)(user)
        # Guess automatically goes towards their team
        if team is None:
            await i.send("You are not on a team!", ephemeral=True)
            return False
        if not await sync_to_async(self.team_scav_enabled)(team):
            await i.send(f"Your team is currently locked out for: {team.lockout_remaining}", ephemeral=True)
            return False

        if team.scavenger_finished:
            await i.send("You're already finished Scav!", ephemeral=True)
            return False
        if role == "Frosh":
            await i.send("Frosh cannot submit scav answers!", ephemeral=True)
            return False
        return True

    def get_team_puzzle_activity(self, team: Team, puzzle: Puzzle):
        return TeamPuzzleActivity.objects.filter(team=team, puzzle=puzzle).first()

    def get_team_active_puzzles(self, team: Team):
        return team.active_puzzles

    def scav_photo_upload(self, file):
        url = self.server + "api/photo"
        files = {'photo': open(file, 'rb')}
        user = os.environ['SERVER_USER']
        passwd = os.environ['SERVER_PASS']
        r = requests.post(url, files=files, auth=HTTPBasicAuth(user, passwd))
        if r.status_code != 200:
            return None
        data = json.loads(r.text)
        return data['id']

    def scav_tree_update(self, team):
        url = self.server + "api/tree?id=" + str(team.group_id)
        user = os.environ['SERVER_USER']
        passwd = os.environ['SERVER_PASS']
        r = requests.post(url, auth=HTTPBasicAuth(user, passwd))
        if r.status_code != 200:
            return False
        return True

    def get_photo(self, id):
        return VerificationPhoto.objects.filter(id=id)[0]

    def set_photo(self, activity, photo):
        activity.verification_photo = photo

    @slash_command(name="guess", description="Makes a scav guess")
    @has_permission("common_models.guess_scavenger_puzzle")
    async def guess(self, i: Interaction, guess: str, file: Optional[nextcord.Attachment] = SlashOption(required=False)):  # noqa: E501
        """Make a guess of the answer to the current scav question."""

        allowed = await self.scav_user_allowed(i)
        if not allowed:
            return

        user = await sync_to_async(self.get_user_from_discord)(i.user)
        team = await sync_to_async(self.get_user_team)(user)

        if team.scavenger_finished:
            i.send("Your team has already finished scav!", ephemeral=True)
            return

        puzzles = await sync_to_async(self.get_team_active_puzzles)(team)
        if len(puzzles) != 1:
            await i.send("Your team has no active puzzles or too many active puzzles!", ephemeral=True)
            return
        puzzle = puzzles[0]
        if not puzzle.enabled:
            team.refresh_scavenger_progress()
            await i.send("An error occurred, please resubmit." +
                         " If this continues please contact planning", ephemeral=True)
            return
        activity = await sync_to_async(self.get_team_puzzle_activity)(team, puzzle)
        p_guess = PuzzleGuess()
        p_guess.value = guess
        p_guess.activity = activity
        await sync_to_async(p_guess.save)()

        if guess.lower() != puzzle.answer.lower():
            try:
                if self.config["incorrect_message"]:
                    await i.send(self.config["incorrect_message"])
                else:
                    await i.send("Incorrect guess")
            except NotFound:
                pass
            return
        if puzzle.require_photo_upload and file is None:
            await i.send("Your guess is correct, but you must attach a verification photo to it when submitting it!")
            return
        elif not puzzle.require_photo_upload:
            await sync_to_async(activity.mark_completed)()
            self.scav_tree_update(team)
            await i.send("Completed scav puzzle")
            return
        self.scav_tree_update(team)
        url = file.url
        name = urlparse(url).path.split('/')[-1]  # Taken from https://stackoverflow.com/a/42341786
        headers = {
            'User-Agent': self.config['user_agent'],  # Have to fake user agent to make requests to discord's cdn
        }
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            await i.send("Failed to open verification image, please resend!", ephemeral=True)
            return

        ext = name.split('.')[-1]
        new_name = str(uuid.uuid4())+'.'+ext
        with open("/tmp/" + new_name, "wb") as f:
            f.write(response.content)
            f.close()
        photo_id = await sync_to_async(self.scav_photo_upload)("/tmp/" + new_name)
        photo = await sync_to_async(self.get_photo)(photo_id)

        await sync_to_async(self.set_photo)(activity, photo)
        await sync_to_async(activity.save)()
        await sync_to_async(activity.mark_completed)()

        sendable_file = await file.to_file()

        verify_channel = i.guild.get_channel(self.config['verify_channel'])
        view = View()
        deny = VerifyButton("Deny", self.scav_deny, photo, i.channel)
        approve = VerifyButton("Approve", self.scav_approve, photo, i.channel)
        view.add_item(deny)
        view.add_item(approve)

        await verify_channel.send(f"Team {team.display_name} submitted a photo for approval" +
                                  f" for question {puzzle.name}", file=sendable_file, view=view)

        await i.send("Completed scav puzzle, please wait for it to be verified!")

    def get_puzzle_from_photo(self, photo: VerificationPhoto):
        return TeamPuzzleActivity.objects.filter(verification_photo=photo).first()

    async def scav_deny(self, i: Interaction, photo: VerificationPhoto, channel: TextChannel):
        puzzle = await sync_to_async(self.get_puzzle_from_photo)(photo)
        puzzle.verification_photo = None
        puzzle.puzzle_completed_at = None
        await sync_to_async(puzzle.save)()
        await sync_to_async(photo.delete)()
        await i.send("Rejected puzzle photo!")
        await channel.send("Your scav answer has been rejected!")

    async def scav_approve(self, i: Interaction, photo: VerificationPhoto, channel: TextChannel):
        await sync_to_async(photo.approve)()
        await i.send("Approved puzzle photo!")
        await channel.send("Your scav answer has been approved!")

    @slash_command(name="question", description="Gets the current scav question")
    async def question(self, i: Interaction):
        """Get questions for current scavenger channel."""
        if i.channel.id not in self.config["team_channels"]:
            await i.send("This is not a scav channel!", ephemeral=True)
            return
        user = await sync_to_async(self.get_user_from_discord)(i.user)
        team = await sync_to_async(self.get_user_team)(user)
        if team is None:
            await i.send("You are not on a team!", ephemeral=True)
            return
        if team.scavenger_finished:
            await i.send("Your team has already completed scav!", ephemeral=True)
            return

        puzzles = await sync_to_async(self.get_team_active_puzzles)(team)
        if len(puzzles) != 1:
            await i.send("Your team has no active puzzles or too many active puzzles!", ephemeral=True)
            return
        puzzle = puzzles[0]
        if not puzzle.enabled:
            team.refresh_scavenger_progress()
            await i.send("An error occurred, please resubmit." +
                         " If this continues please contact planning", ephemeral=True)
            return
        if puzzle.puzzle_file:
            f = open(puzzle.puzzle_file.path, "rb")
            f_name = puzzle.puzzle_file_display_filename
            if f_name is None:
                f_name = puzzle.puzzle_file.name
            await i.send(puzzle.puzzle_text, files=File(f, filename=f_name))
        else:
            await i.send(puzzle.puzzle_text)

    def get_team_by_name(self, team_name):
        return Team.objects.filter(display_name__iexact=team_name).first()

    def get_team_by_role(self, role):
        return Team.objects.filter(group=DiscordRole.objects.filter(role_id=role).first().group).first()

    @slash_command(name="scav_lock", description="Lock a team's scav")
    @has_permission("common_models.manage_scav")
    async def scav_lock(self, i: Interaction, team_name: Role, minutes: int = 15):
        """Lock a team's scav"""

        team = await sync_to_async(self.get_team_by_role)(team_name.id)
        if team is None:
            await i.send("Invalid team", ephemeral=True)
            return
        await sync_to_async(team.scavenger_lock)(minutes)

        await i.send(f"Scav locked for {minutes} minutes.", ephemeral=True)

    def team_scav_unlock(self, team: Team) -> None:
        team.scavenger_unlock

    @slash_command(name="scav_unlock", description="Unlock a team's scav")
    @has_permission("common_models.manage_scav")
    async def scav_unlock(self, i: Interaction, team_name: Role):
        """Unlock a team's scav"""

        team = await sync_to_async(self.get_team_by_role)(team_name.id)
        if team is None:
            await i.send("Invalid team", ephemeral=True)
            return

        await sync_to_async(self.team_scav_unlock)(team)

        await i.send("Scav unlocked.", ephemeral=True)

    @slash_command(name="hint", description="Requests a hint for the question")
    async def hint(self, i: Interaction):
        """Request hint for the question."""

        user = await sync_to_async(self.get_user_from_discord)(i.user)
        team = await sync_to_async(self.get_user_team)(user)
        if team is None:
            await i.send("You are not on a team!", ephemeral=True)
            return
        if team.scavenger_finished:
            await i.send("Your team has already completed scav!", ephemeral=True)
            return
        await i.send("This is not implemented!", ephemeral=True)
        # TODO: Implement this
        return


def setup(bot):
    bot.add_cog(Scav(bot))
# endregion
