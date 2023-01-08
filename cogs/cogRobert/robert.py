from nextcord.ext import commands
from nextcord import slash_command, Interaction
from common_models.models import RobertEntry
from asgiref.sync import sync_to_async


class Robert(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config["module_settings"]["robert"]

    def robert_add_sync(self, type: int, id: int):
        entry = RobertEntry(user=id, type=type)
        entry.save()

    @slash_command(name="robert_add", description="Adds a robert to the queue")
    async def robert_add(self, i: Interaction, type: int):
        if type > 3 or type < 1:
            await i.send("The type must be between 1-3 inclusive", ephemeral=True)
            return
        await sync_to_async(self.robert_add_sync)(type, i.user.id)
        await i.send("You have been added to the queue", ephemeral=True)
        channel = i.guild.get_channel(self.config['updates_channel'])
        message = "**Robert Queue**\n"
        queue = await sync_to_async(self.get_queue)()
        for robert in queue:
            user = i.guild.get_member(robert.user)
            message += str(robert.type) + ": " + user.display_name + " : From " + str(robert.created)
            message += "\n"
        await channel.send(message)

    def get_queue(self):
        roberts = list(RobertEntry.objects.order_by('-type', 'created'))
        return roberts

    def robert_next_sync(self):
        roberts = self.get_queue()
        if len(roberts) == 0:
            return None
        robert = roberts[0]
        ret = (robert.user, robert.type, robert.created)
        robert.delete()
        return ret

    @slash_command(name="robert_next", description="Gets the next robert from the queue")
    async def robert_next(self, i: Interaction):
        robert = await sync_to_async(self.robert_next_sync)()
        if robert is None:
            await i.send("There are no roberts in the queue!", ephemeral=True)
            return
        user = i.guild.get_member(robert[0])
        mention = user.mention
        await i.send(mention + " : Type " + str(robert[1]) + " : From " + str(robert[2]), ephemeral=True)

    @slash_command(name="robert_queue", description="Gets the whole robert queue")
    async def robert_queue(self, i: Interaction):
        queue = await sync_to_async(self.get_queue)()
        if len(queue) == 0:
            await i.send("There are no roberts in the queue!", ephemeral=True)
            return
        message = ""
        for robert in queue:
            user = i.guild.get_member(robert.user)
            message += str(robert.type) + ": " + user.display_name + " : From " + str(robert.created)
            message += "\n"
        await i.send(message, ephemeral=True)


def setup(bot):
    """Setup Coin Cog."""
    bot.add_cog(Robert(bot))
