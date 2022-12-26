# region Imports
import logging
from typing import Optional, Union
# import datetime as dt

import nextcord
from nextcord.ext import commands, application_checks
from nextcord import slash_command, Interaction, Member, SlashOption, TextChannel
from nextcord.ui import View, Button, Item
from typing import Optional

from common_models.models import *

from django.db.models import ImageField, FileField
from django.core.files import File

from EngFroshBot import EngFroshBot
from asgiref.sync import sync_to_async
import requests
from urllib.parse import urlparse
import uuid
# endregion


logger = logging.getLogger("Cogs.Scav")

class VerifyButton(Button):
    def __init__(self,label:str, callback, photo: VerificationPhoto, channel: TextChannel):
        self.callback_fun = callback
        self.photo = photo
        self.channel = channel
        super().__init__(label=label)
    async def callback(self, i: Interaction):
        await self.callback_fun(i,self.photo, self.channel)

class Scav(commands.Cog):
    def __init__(self, bot: EngFroshBot):
        self.bot = bot
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
        user = DiscordUser.objects.filter(discord_username=author.name,discriminator=author.discriminator).first()
        if user == None:
            return None
        return UserDetails.objects.filter(user=user.user).first()
    def get_user_team(self, user: UserDetails):
        frosh_groups = FroshRole.objects.all()
        names = []
        for g in frosh_groups:
            names += [g.name]
        team = user.user.groups.exclude(name__in=names).first()
        if team == None:
            return None
        return Team.objects.filter(group=team).first()
    def get_user_role(self, user: UserDetails):
        frosh_groups = FroshRole.objects.all()
        names = []
        for g in frosh_groups:
            names += [g.name]
        role = user.user.groups.filter(name__in=names).first()
        if role == None:
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

        if not i.channel.id in self.config['team_channels']:
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
        if team == None:
            await i.send("You are not on a team!", ephemeral=True)
            return False
        if not await sync_to_async(self.team_scav_enabled)(team):
            await i.send(f"Your team is currently locked out for: {team.lockout_remaining}", ephemeral=True)
            return False

        if team.scavenger_finished:
            await i.send("You're already finished Scav!", ephemeral=True)
            return False

        return True
    def get_team_puzzle_activity(self, team: Team, puzzle: Puzzle):
        return TeamPuzzleActivity.objects.filter(team=team,puzzle=puzzle).first()
    def get_team_active_puzzles(self, team: Team):
        return team.active_puzzles
    @slash_command(name="guess", description="Makes a scav guess")
    async def guess(self, i: Interaction, guess: str, file: Optional[nextcord.Attachment] = SlashOption(required=False)):
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
            await i.send("Your team has no active puzzles or too many active puzzles!",ephemeral=True)
            return
        puzzle = puzzles[0]
        if not puzzle.enabled:
            team.refresh_scavenger_progress()
            await i.send("An error occurred, please resubmit. If this continues please contact planning", ephemeral=True)
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
            await i.send("Your guess is correct, however you must attach a verification photo to it when submitting it!")
            return
        elif not puzzle.require_photo_upload:
            await sync_to_async(activity.mark_completed)()
            await i.send("Completed scav puzzle")
            return
        url = file.url
        name = urlparse(url).path.split('/')[-1] # Taken from https://stackoverflow.com/a/42341786
        headers = {
            'User-Agent': self.config['user_agent'], # Have to fake user agent to make requests to discord's cdn
        }
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            await i.send("Failed to open verification image, please resend!",ephemeral=True)
            return
        photo = VerificationPhoto()
        ext = name.split('.')[-1]
        new_name = str(uuid.uuid4())+'.'+ext
        verify_dir = self.bot.config['verify_dir']
        verify_prefix = self.bot.config['verify_prefix']
        with open(verify_dir+new_name,"wb") as f:
            f.write(response.content)
            f.close()
        photo.photo.name = verify_prefix+new_name # This https://stackoverflow.com/a/66161155 answer's poster is a literal saint
        await sync_to_async(photo.save)()

        activity.verification_photo = photo
        await sync_to_async(activity.save)()
        await sync_to_async(activity.mark_completed)()
        
        sendable_file = await file.to_file()

        verify_channel = i.guild.get_channel(self.config['verify_channel'])
        view = View()
        deny = VerifyButton("Deny", self.scav_deny, photo, i.channel)
        approve = VerifyButton("Approve", self.scav_approve, photo, i.channel)
        view.add_item(deny)
        view.add_item(approve)

        await verify_channel.send(f"Team {team.display_name} submitted a photo for approval for question {puzzle.name}", file=sendable_file, view=view)
        
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
    def get_team_active_puzzles(self, team: Team) -> List[Puzzle]:
        return team.active_puzzles
    @slash_command(name="question", description="Gets the current scav question")
    async def question(self, i: Interaction):
        """Get questions for current scavenger channel."""
        if not i.channel.id in self.config["team_channels"]:
            await i.send("This is not a scav channel!",ephemeral=True)
            return
        user = await sync_to_async(self.get_user_from_discord)(i.user)
        team = await sync_to_async(self.get_user_team)(user)
        if team == None:
            await i.send("You are not on a team!", ephemeral=True)
            return
        if team.scavenger_finished:
            await i.send("Your team has already completed scav!",ephemeral=True)
            return

        puzzles = await sync_to_async(self.get_team_active_puzzles)(team)
        if len(puzzles) != 1:
            await i.send("Your team has no active puzzles or too many active puzzles!",ephemeral=True)
            return
        puzzle = puzzles[0]
        if not puzzle.enabled:
            team.refresh_scavenger_progress()
            await i.send("An error occurred, please resubmit. If this continues please contact planning", ephemeral=True)
            return
        if puzzle.puzzle_file:
            f = open(puzzle.puzzle_file.path, "rb")
            f_name = puzzle.puzzle_file_display_filename
            if f_name == None:
                f_name = puzzle.puzzle_file.name
            await i.send(puzzle.puzzle_text, files=File(f,filename=f_name))
        else:
            await i.send(puzzle.puzzle_text)
    def get_team_by_name(self, team_name):
        return Team.objects.filter(display_name__iexact=team_name).first()
    @slash_command(name="scav_lock", description="Lock a team's scav", dm_permission=False, default_member_permissions=8)
    @application_checks.has_permissions(administrator=True)
    async def scav_lock(self, i: Interaction, team_name: str, minutes: int = 15):
        """Lock a team's scav"""

        team = await sync_to_async(self.get_team_by_name)(team_name)
        if team == None:
            await i.send("Invalid team", ephemeral=True)
            return
        await sync_to_async(team.scavenger_lock)(minutes)

        await i.send(f"Scav locked for {minutes} minutes.", ephemeral=True)

    def team_scav_unlock(self, team: Team) -> None:
        team.scavenger_unlock

    @slash_command(name="scav_unlock", description="Unlock a team's scav", dm_permission=False, default_member_permissions=8)
    @application_checks.has_permissions(administrator=True)
    async def scav_unlock(self, i: Interaction, team_name: str):
        """Unlock a team's scav"""

        team = await sync_to_async(self.get_team_by_name)(team_name)
        if team == None:
            await i.send("Invalid team", ephemeral=True)
            return

        await sync_to_async(self.team_scav_unlock)(team)

        await i.send("Scav unlocked.", ephemeral=True)

    @slash_command(name="hint", description="Requests a hint for the question")
    async def hint(self, i: Interaction):
        """Request hint for the question."""

        user = await sync_to_async(self.get_user_from_discord)(i.user)
        team = await sync_to_async(self.get_user_team)(user)
        if team == None:
            await i.send("You are not on a team!", ephemeral=True)
            return
        if team.scavenger_finished:
            await i.send("Your team has already completed scav!",ephemeral=True)
            return
        await i.send("This is not implemented!", ephemeral=True)
        #TODO: Implement this
        return

def setup(bot):
    bot.add_cog(Scav(bot))
# endregion

