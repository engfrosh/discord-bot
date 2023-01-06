import logging
from nextcord.ext import commands
from EngFroshBot import EngFroshBot
from nextcord import slash_command, Interaction, Member
import random
from common_models.models import EuchreCard, EuchrePlayer, EuchreTrick, EuchreTeam, EuchreGame
from asgiref.sync import sync_to_async

logger = logging.getLogger("Cogs.Moderation")


class Euchre(commands.Cog):

    def __init__(self, bot: EngFroshBot) -> None:
        """Management COG init"""
        self.bot = bot

    def shuffle(self, players):
        deck = []
        for suit in "HDCS":
            for rank in range(7, 15):  # Ace is 14 and 7 is 7
                deck += [(suit, rank)]
        for i in range(len(players)):
            for index in range(5):  # Deal 5 cards to each player
                draw = deck.pop(random.randint(0, len(deck) - 1))
                card = EuchreCard(suit=draw[0], rank=draw[1], player=players[i])
                card.save()
        trump = deck.pop(random.randint(0, len(deck) - 1))
        trump_card = EuchreCard(suit=trump[0], rank=trump[1])
        trump_card.save()
        extra = deck.pop(random.randint(0, len(deck) - 1))
        extra_card = EuchreCard(suit=extra[0], rank=extra[1])  # This card is used in case no trump is selected
        extra_card.save()
        return (trump_card, extra_card)

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
            index = random.randint(0, len(players) - 1)
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
        cards = self.shuffle(players)
        trick = EuchreTrick(opener=cards[0], selection=True)
        trick.save()
        game = EuchreGame(dealer=dealer, next_dealer=next_dealer, current_trick=trick,
                          extra_card=cards[1], selector=next_dealer)
        game.save()
        team1.game = game
        team2.game = game
        team1.save()
        team2.save()
        return game

    def get_teams(self, game):
        teams = []
        query = EuchreTeam.objects.filter(game=game)
        for team in query:
            p_query = EuchrePlayer.objects.filter(team=team)
            players = []
            for player in p_query:
                players += [player.id]
            teams += [players]
        return teams

    @slash_command(name="euchre_start", description="Starts a Euchre game")
    async def start_game(self, i: Interaction, p1: Member, p2: Member, p3: Member, p4: Member):
        players = [p1, p2, p3, p4]  # Probably could take the input better
        if len(set(players)) != len(players):
            await i.send("All players must be unique!", ephemeral=True)
            return
        game = await sync_to_async(self.setup_game)(players)
        next = i.guild.get_member(game.selector.id)
        next_mention = next.mention
        dealer = i.guild.get_member(game.dealer_id)
        dealer_mention = dealer.mention
        teams = await sync_to_async(self.get_teams)(game)
        await i.send("Euchre game started! Dealer is " + dealer_mention + "\n" +
                     next_mention + " goes first!\nTrump to be selected is " +
                     game.current_trick.opener.name)
        message = ""
        count = 1
        for team in teams:
            ment = "Team "+str(count)
            for p in team:
                ment += " " + i.guild.get_member(p).mention
            count += 1
            message += ment + "\n"
        await i.send(message)

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
        game.declarer = player.team
        dealer = game.dealer
        message = ""
        if card is None:
            if trick.count >= 4:
                return ("You must select a card to become trump!", True)
            else:
                return ("You must select a card to replace!", True)
        card_value = self.get_card_from_name(card, player)
        if card_value is None:
            return ("Unable to find that card!", True)
        if trick.count < 4:
            if player.team == dealer.team and player != dealer:
                message += "You are going alone!\n"
                player.team.going_alone = player
                player.team.save()
            game.trump = trick.opener.suit
            trick.opener.player = player
            trick.opener.save()
            trick.opener = None
            trick.selection = False
            trick.save()
            card_value.played = True
            card_value.save()
            game.selector = game.next_dealer
            game.save()
            return (message + "Trump has been selected!", False, game.next_dealer.id)
        else:
            if player.team == dealer.team and player != dealer:
                message += "You are going alone!\n"
                player.team.going_alone = player
                player.team.save()
            game.trump = card_value.suit
            game.selector = game.next_dealer
            game.save()
            card_value.played = True
            card_value.save()
            game.extra_card.player = player
            game.extra_card.save()
            trick.opener = None
            trick.selection = False
            trick.save()
            return (message + "Trump has been selected and is " + card_value.name.split()[0],
                    False, game.next_dealer.id)

    @slash_command(name="euchre_accept",
                   description="Accepts the current card as trump, alternatively selects one" +
                               " of your own cards as trump")
    async def euchre_accept(self, i: Interaction, card: str):
        id = i.user.id
        player = await sync_to_async(EuchrePlayer.objects.filter(id=id).first)()
        result = await sync_to_async(self.euchre_accept_sync)(player, card)
        await i.send(result[0], ephemeral=result[1])
        if result[1] is False:
            next = i.guild.get_member(result[2])
            next_mention = next.mention
            await i.send("It is " + next_mention + "'s turn")

    def euchre_reject_sync(self, player):
        game = player.team.game
        trick = game.current_trick
        if not trick.selection:
            return ("Trump has already been selected!", True, True)
        if game.selector != player:
            return ("It is not your turn!", True, True)
        trick.count += 1
        trick.save()
        new_selector = game.compute_selector()
        return (trick.count >= 4, new_selector, False)

    @slash_command(name="euchre_reject", description="Rejects the current card as trump")
    async def euchre_reject(self, i: Interaction):
        id = i.user.id
        player = await sync_to_async(EuchrePlayer.objects.filter(id=id).first)()
        result = await sync_to_async(self.euchre_reject_sync)(player)
        if not result[2]:
            next = i.guild.get_member(result[1].id)
            next_mention = next.mention
            await i.send("It is now "+next_mention + "'s turn ot accept or reject trump!")
            if result[0]:
                await i.send("You can select any card in your hand to become trump!")
        else:
            await i.send(result[0], ephemeral=True)

    def euchre_play_sync(self, player, card_name):
        game = player.team.game
        if game.selector != player:
            return ("It is not your turn!", True)
        card = self.get_card_from_name(card_name, player)
        if card is None:
            return ("Unable to find that card!", True)
        trick = game.current_trick
        if trick.selection:
            return ("Trump has not been chosen!", True)
        opposites = {"D": "H", "H": "D", "C": "S", "S": "C"}
        if trick.opener is not None:
            open_suit = trick.opener.suit
            if open_suit == opposites[game.trump] and trick.opener.rank == 11:
                open_suit = game.trump
            card_suit = card.suit
            if card_suit == opposites[game.trump] and card.rank == 11:
                card_suit = game.trump
            if player.can_follow_suit(game) and card_suit != open_suit:
                return ("You must follow suit!", True)
        card.played = True
        card.save()
        next_selector = game.compute_selector().id
        if trick.opener is None:
            trick.opener = card
            trick.highest = card
            trick.save()
            return ("Played card "+card_name, False, False, next_selector)
        highest = trick.highest
        if card.suit == game.trump and card.rank == 11:
            # Right bower
            trick.highest = card
            trick.save()
        elif card.suit == opposites[game.trump] and card.rank == 11 and not highest.is_bower(game.trump):
            # Left bower and right bower hasn't been played
            trick.highest = card
            trick.save()
        elif card.suit == game.trump:
            if not highest.is_bower(game.trump):
                if highest.suit != game.trump:
                    # any trump is higher than all non trump cards
                    trick.highest = card
                    trick.save()
                elif highest.rank < card.rank:
                    # these 2 are not able to equal because each card is unique
                    trick.highest = card
                    trick.save()
        elif card.suit == trick.opener.suit:
            if not highest.is_bower(game.trump) and highest.suit != game.trump and card.rank > highest.rank:
                trick.highest = card
                trick.save()
        highest = trick.highest  # This must be run again in case it changed above
        if next_selector == trick.opener.player.id:
            # End of turn
            winning_team = highest.player.team
            winning_team.tricks_won += 1
            winning_team.save()
            if game.check_for_winner():
                winning_team.points += game.points
                winning_team.save()
                players = []
                for team in EuchreTeam.objects.filter(game=game):
                    team.tricks_won = 0
                    team.save()
                    players += list(EuchrePlayer.objects.filter(team=team))
                new_next_dealer = game.compute_dealers(game.dealer)
                game.dealer = game.next_dealer
                game.next_dealer = new_next_dealer
                game.selector = game.next_dealer
                cards = self.shuffle(players)
                game.extra_card = cards[1]
                game.save()
                trick.opener = cards[0]
                trick.highest = None
                trick.selection = True
                trick.count = 0
                trick.save()
                team = []
                for player in EuchrePlayer.objects.filter(team=highest.player.team):
                    team += [player.id]
                return ("Played card "+card_name, False, True, True, winning_team.points,
                        team, game.dealer, game.selector, game.current_trick.opener.name)
            trick.opener = None
            trick.highest = None
            trick.selection = False
            trick.count = 0
            trick.save()
            team = []
            game.selector = highest.player
            game.save()
            for player in EuchrePlayer.objects.filter(team=highest.player.team):
                team += [player.id]
            return ("Played card "+card_name, False, True, False, highest.player.id, team)
        return ("Played card "+card_name, False, False, next_selector)

    @slash_command(name="euchre_play", description="Plays a card from your hand")
    async def euchre_play(self, i: Interaction, card: str):
        id = i.user.id
        player = await sync_to_async(EuchrePlayer.objects.filter(id=id).first)()
        result = await sync_to_async(self.euchre_play_sync)(player, card)
        await i.send(result[0], ephemeral=result[1])
        if not result[1] and result[2]:
            # Trick is over
            team = result[5]
            data = ""
            for p in team:
                user = i.guild.get_member(p).mention
                data += user + " "
            if not result[3]:
                data += "won this trick!"
                await i.send(data)
                next = i.guild.get_member(result[4]).mention
                await i.send("Its " + next + "'s turn!")
            else:
                # game is over
                data += "won this game and now have " + str(result[4]) + "points!"
                dealer_mention = i.guild.get_member(result[5]).mention
                next_mention = i.guild.get_member(result[6]).mention
                await i.send(data + "\nNew dealer is " + dealer_mention + "\n" + next_mention +
                             " goes first!\nTrump to be selected is " + result[7])
        elif not result[1] and not result[2]:
            mention = i.guild.get_member(result[3]).mention
            await i.send("Its " + mention + "'s turn!")

    def euchre_end_sync(self, player):
        game = player.team.game
        teams = EuchreTeam.objects.filter(game=game)
        points = []
        for team in teams:
            players = EuchrePlayer.objects.filter(team=team)
            points += [(players[0].id, players[1].id, team.points)]
        game.delete()
        return points

    @slash_command(name="euchre_end", description="Ends a Euchre game")
    async def euchre_end(self, i: Interaction):
        id = i.user.id
        player = await sync_to_async(EuchrePlayer.objects.filter(id=id).first)()
        result = await sync_to_async(self.euchre_end_sync)(player)
        message = "Ended game with scores:\n"
        for team in result:
            p1 = i.guild.get_member(team[0]).mention
            p2 = i.guild.get_member(team[1]).mention
            message += p1 + " " + p2 + " : " + team[2] + " points!\n"
        await i.send(message)

    def euchre_status_sync(self, player):
        game = player.team.game
        teams = EuchreTeam.objects.filter(game=game)
        output = []
        for team in teams:
            players = []
            p = EuchrePlayer.objects.filter(team=team)
            for player in p:
                players += [player.id]
            output += [(players, team.tricks_won, team.points)]
        return output

    @slash_command(name="euchre_status", description="Gets the current status of a Euchre game")
    async def euchre_status(self, i: Interaction):
        id = i.user.id
        player = await sync_to_async(EuchrePlayer.objects.filter(id=id).first)()
        output = await sync_to_async(self.euchre_status_sync)(player)
        message = ""
        for team in output:
            mention = ""
            for player in team[0]:
                mention += i.guild.get_member(player).mention + " "
            mention += ": " + str(team[1]) + " Trick(s) : " + str(team[2]) + " Point(s)"
            message += mention + "\n"
        await i.send(message, ephemeral=True)


def setup(bot):
    bot.add_cog(Euchre(bot))
