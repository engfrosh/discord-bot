import logging
from nextcord.ext import commands
from EngFroshBot import EngFroshBot
from typing import Optional
from nextcord import slash_command, Interaction, PermissionOverwrite, TextChannel, Role, Permissions, SlashOption, Member
import random
from common_models.models import EuchreCard, EuchrePlayer, EuchreTrick, EuchreTeam, EuchreGame
from asgiref.sync import sync_to_async

logger = logging.getLogger("Cogs.Moderation")


class Euchre(commands.Cog):

    def __init__(self, bot: EngFroshBot) -> None:
        """Management COG init"""
        self.bot = bot
    
    def setup_game(self, players):
        for i in range(len(players)):
            players[i] = EuchrePlayer.objects.get_or_create(id=players[i].id)[0]
            players[i].team = None
            players[i].save()
            cards = EuchreCard.objects.filter(player=players[i])
            for card in cards:
                card.delete()
        count = 0
        team1 = EuchreTeam()
        dealer = None
        team1.save()
        while count < 2:
            index = random.randint(0,len(players)-1)
            if players[index].team is None:
                players[index].team = team1
                players[index].save()
                if count == 0:
                    dealer = players[index]
                count += 1
        team2 = EuchreTeam()
        team2.save()
        next_dealer = None
        count = 0
        for i in range(len(players)):
            if players[i].team is None:
                if count == 0:
                    next_dealer = players[i]
                players[i].team = team2
                players[i].save()
                count += 1
        deck = []
        for suit in "HDCS":
            for rank in range(7,15):  # Ace is 14 and 7 is 7
                deck += [(suit, rank)]
        for i in range(len(players)):
            for index in range(5):  # Deal 5 cards to each player
                draw = deck.pop(random.randint(0, len(deck) - 1))
                card = EuchreCard(suit=draw[0], rank=draw[1], player=players[i])
                card.save()
        trump = deck.pop(random.randint(0, len(deck) - 1))
        trump_card = EuchreCard(suit=trump[0], rank=trump[1])
        trump_card.save()
        trick = EuchreTrick(opener=trump_card, selection=True)
        trick.save()
        extra = deck.pop(random.randint(0, len(deck) - 1))
        extra_card = EuchreCard(suit=extra[0], rank=extra[1])  # This card is used in case no trump is selected and someone chooses it
        extra_card.save()
        game = EuchreGame(dealer=dealer, next_dealer=next_dealer, current_trick=trick, extra_card=extra_card, selector=next_dealer)
        game.save()
        team1.game = game
        team2.game = game
        team1.save()
        team2.save()
        return game

    @slash_command(name="euchre_start", description="Starts a Euchre game")
    async def start_game(self, i: Interaction, p1: Member, p2: Member, p3: Member, p4: Member):
        players = [p1,p2,p3,p4]  # Probably could take the input better
        game = await sync_to_async(self.setup_game)(players)
        next = i.guild.get_member(game.selector.id)
        next_mention = next.mention
        dealer = i.guild.get_member(game.dealer_id)
        dealer_mention = dealer.mention
        await i.send("Euchre game started! Dealer is "+dealer_mention+"\n"+next_mention+" goes first!\nTrump to be selected is "+game.current_trick.opener.name)
    
    def get_player_cards(self, player):
        return list(EuchreCard.objects.filter(player=player).exclude(played=True))

    @slash_command(name="euchre_hand", description="Shows your current cards")
    async def show_hand(self, i: Interaction):
        id = i.user.id
        player = await sync_to_async(EuchrePlayer.objects.filter(id=id).first)()
        cards = await sync_to_async(self.get_player_cards)(player=player)
        message = "Your cards are:\n"
        for card in cards:
            message += "- "+card.name+"\n"
        await i.send(message, ephemeral=True)

    def get_card_from_name(self, name, player):
        for card in EuchreCard.objects.filter(player=player).exclude(played=True):
            if card.name.lower() == name.lower():
                return card
        return None
    
    def euchre_accept_sync(self, player, card):
        game = player.team.game
        trick = game.current_trick
        if not trick.selection:
            return ("Game is not in trump selection status!", True)
        if game.selector != player:
            return ("It is not your turn!", True)

        if trick.count < 4:
            if card is not None:
                return ("You cannot select your own card until everyone has passed!", True)
            game.trump = trick.opener.suit
            trick.opener = None
            trick.selection = False
            trick.save()
            game.save()
            return ("Trump has been selected!", False, game.next_dealer.id)
        else:
            if card is None:
                return ("You must select a card to become trump!", True)
            card_value = self.get_card_from_name(card, player)
            if card_value is None:
                return ("Unable to find that card!", True)
            game.trump = card_value.suit
            game.save()
            card_value.player = None
            card_value.save()
            game.extra_card.player = player
            game.extra_card.save()
            trick.opener = None
            trick.selection = False
            trick.save()
            return ("Trump has been selected and is " + card_value.name.split()[0], False, game.next_dealer.id)

    @slash_command(name="euchre_accept", description="Accepts the current card as trump, alternatively selects one of your own cards as trump")
    async def euchre_accept(self, i: Interaction, card: Optional[str] = None):
        id = i.user.id
        player = await sync_to_async(EuchrePlayer.objects.filter(id=id).first)()
        result = await sync_to_async(self.euchre_accept_sync)(player,card)
        await i.send(result[0], ephemeral=result[1])
        if result[1] == False:
            next = i.guild.get_member(result[2])
            next_mention = next.mention
            await i.send("It is " + next_mention + "'s turn")

    def euchre_reject_sync(self, player):
        game = player.team.game
        trick = game.current_trick
        trick.count += 1
        trick.save()
        new_selector = game.compute_selector()
        return (trick.count >= 4,new_selector)

    @slash_command(name="euchre_reject", description="Rejects the current card as trump")
    async def euchre_reject(self, i: Interaction):
        id = i.user.id
        player = await sync_to_async(EuchrePlayer.objects.filter(id=id).first)()
        result = await sync_to_async(self.euchre_reject_sync)(player)
        next = i.guild.get_member(result[1].id)
        next_mention = next.mention
        await i.send("It is now "+next_mention + "'s turn ot accept or reject trump!")
        if result[0]:
            await i.send("You can select any card in your hand to become trump!")

    def euchre_play_sync(self, player, card_name):
        game = player.team.game
        if game.selector != player:
            return ("It is not your turn!", True)
        card = self.get_card_from_name(card_name, player)
        if card is None:
            return ("Unable to find that card!", True)
        card.played = True
        card.save()
        trick = game.current_trick
        if trick.selection == True:
            return ("Trump has not been chosen!", True)
        next_selector =  game.compute_selector().id
        if trick.opener is None:
            trick.opener = card
            trick.highest = card
            trick.save()
            return ("Played card "+card_name, False, False, next_selector)
        highest = trick.highest
        if card.suit == game.trump:
            if highest.suit != game.trump:
                # any trump is higher than all non trump cards
                trick.highest = card
                trick.save()
            elif trick.highest.rank < card.rank:
                # these 2 are not able to equal because each card is unique
                trick.highest = card
                trick.save()

        elif card.suit == trick.opener.suit:
            if highest.suit != game.trump and card.rank > highest.rank:
                trick.highest = card
                trick.save()

        if player == trick.opener.player:
            # End of turn
            winning_team = highest.player.team
            winning_team.tricks_won += 1
            winning_team.save()
            return ("Played card "+card_name, False, True)
        return ("Played card "+card_name, False, False, next_selector)

    def get_trick_winner(self, player):
        trick = player.team.game.current_trick
        team = trick.highest.team
        result = []
        for player in EuchrePlayer.objects.filter(team=team):
            result += [player.id]
        return result
    @slash_command(name="euchre_play", description="Plays a card from your hand")
    async def euchre_play(self, i: Interaction, card: str):
        id = i.user.id
        player = await sync_to_async(EuchrePlayer.objects.filter(id=id).first)()
        result = await sync_to_async(self.euchre_play_sync)(player, card)
        await i.send(result[0], ephemeral=result[1])
        if not result[1] and result[2]:
            # Trick is over
            team = await sync_to_async(get_trick_winner)(player)
            data = ""
            for p in team:
                user = i.guild.get_member(p.id).mention
                data += user + " "
            data += "won this trick!"
            await i.send(data)
        elif not result[1] and not result[2]:
            mention = i.guild.get_member(result[3]).mention
            await i.send("Its "+mention+"'s turn!")

def setup(bot):
    bot.add_cog(Euchre(bot))
