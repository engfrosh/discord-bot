import logging
from nextcord.ext import commands, application_checks
from nextcord import slash_command, Interaction
from EngFroshBot import EngFroshBot
from common_models.models import Team
from asgiref.sync import sync_to_async

logger = logging.getLogger("Cogs.Coin")


class Coin(commands.Cog):
    def __init__(self, bot: EngFroshBot) -> None:
        self.bot = bot
        self.config = bot.config["module_settings"]["coin"]

    @slash_command(name="set_coin", description="Changes a team's coin value",
                    dm_permission=False, default_member_permissions=8)
    @application_checks.has_permissions(administrator=True)
    async def coin(self, i: Interaction, team, amount):
        """Change team's coin: coin [team] [amount]"""
        res = await sync_to_async(self.update_coin_amount)(int(amount), team)

        if res:
            # TODO change so it sends to that team's update channel
            await i.send(f"{team} You got {amount} scoin!")
            await self.update_coin_board(i)
        else:
            await i.send(f"Sorry, no team called {team}, please try again.", ephemeral=True)
    def update_coin_amount(self, amount, team):
        teams = Team.objects.filter(display_name__iexact=team)
        team_data = teams.first()
        if team_data == None:
            return False
        team_data.coin_amount=amount
        team_data.save()
        return True
    def get_all_frosh_teams(self):
        return list(Team.objects.all())
    async def update_coin_board(self, i: Interaction):
        """Update the coin standings channel."""

        logger.debug("Updating coin board...")
        teams = await sync_to_async(self.get_all_frosh_teams)()

        teams.sort(key=lambda team: team.coin_amount, reverse=True)

        msg = f"```\n{self.config['scoreboard']['header']}\n"
        name_padding = self.config['scoreboard']['name_length']
        coin_padding = self.config['scoreboard']['coin_length']

        cur_place = 0
        cur_coin = None
        next_place = 1

        for team in teams:
            s = f"{self.config['scoreboard']['row']}\n"

            team_name = team.display_name
            coin_amount = team.coin_amount

            if coin_amount == cur_coin:
                # If there is a tie
                place = cur_place
                next_place += 1
            else:
                place = next_place
                cur_place = next_place
                next_place += 1
                cur_coin = coin_amount

            msg += s.format(
                place=place, team_name=f"{team_name}{' ' * (name_padding - len(str(team_name)))}",
                coin_amount=f"{coin_amount}{' ' * (coin_padding - len(str(coin_amount)))}")
        msg += "```"

        logger.debug(f"Got coin message: {msg}")
        channel = self.config["scoreboard_channel"]
        logger.debug(f"Sending to: {channel}")
        await i.guild.get_channel(channel).send(msg)


def setup(bot):
    """Setup Coin Cog."""
    bot.add_cog(Coin(bot))
