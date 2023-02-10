import common_models.models as md
from django.contrib.auth.models import User
import random
import string


def add_pronoun(name: str, order: int, user: User):
    name = name.title()
    pronoun = md.Pronoun(name=name, order=order, user=user)
    pronoun.save()


def compute_discord_name(user_id: int):
    disc_user = md.DiscordUser.objects.filter(id=user_id).first()
    if disc_user is None:
        return None
    user = disc_user.user
    details = md.UserDetails.objects.filter(user=user).first()
    if details.override_nick is not None:
        return details.override_nick
    pronouns = details.pronouns
    name = user.first_name + " " + user.last_name
    if len(pronouns) > 0:
        name += " ("
        for i in range(len(pronouns)-1):
            if len(name + pronouns[i].name + " ") > 31:
                break
            name += pronouns[i].name + " "
        name += pronouns[len(pronouns)-1].name + ")"
    return name


def create_discord_user(first, last, id, username, discriminator):
    name = first + " " + last
    username = name.replace(" ", "_") + "-" + "".join(random.choice(string.ascii_letters + string.digits)
                                                      for i in range(8))
    user = User(first_name=first, last_name=last, username=username)
    user.save()
    details = md.UserDetails(user=user, name=name)
    details.save()
    link_discord_user(user, id, username, discriminator)


def link_discord_user(user: User, id: int, username: str, discriminator: int):
    disc_user = md.DiscordUser(user=user, id=id, discord_username=username,
                               discriminator=discriminator)
    disc_user.save()
    return disc_user


def unlink_discord_user(user: User):
    disc_user = md.DiscordUser.objects.filter(user=user).first()
    if disc_user is not None:
        disc_user.delete()


def create_discord_pronoun_message() -> str:
    text = "Select your pronouns:\n"
    for p in md.PronounOption.objects.all():
        text += p.emote + " " + p.name + "\n"
    return text


def get_pronoun_emotes() -> list[str]:
    results = []
    for p in md.PronounOption.objects.all():
        results += [p.emote]
    return results


def discord_add_pronoun(emote, id):
    disc_user = md.DiscordUser.objects.filter(id=id).first()
    if disc_user is None:
        return False
    user = disc_user.user
    details = md.UserDetails.objects.filter(user=user).first()
    pronouns = md.PronounOption.objects.all()
    pronoun = None
    for p in pronouns:
        if p.emote == emote:
            pronoun = p
            break
    if pronoun is None:
        return False
    for p in details.pronouns:
        if p.name == pronoun.name:
            return False
    add_pronoun(pronoun.name, details.next_pronoun, user)
    return True


def register_message(type: str, id: int):
    message = md.DiscordMessage(type=type, id=id)
    message.save()
    return message


def get_messages(type: str):
    return list(md.DiscordMessage.objects.filter(type=type).all())


def create_pronoun(name: str, emote: str):
    opt = md.PronounOption(name=name, emote=emote)
    opt.save()
    return opt
