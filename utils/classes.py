from discord import ApplicationCommandError
import discord
from datetime import datetime


class CommandDisabledError(ApplicationCommandError):
    pass


class InsufficientPermission(ApplicationCommandError):
    pass


class Event:
    """event_t = {
        "event_id": event.event_id,
        "host": event.host,
        "name": event.event_name,
        "time": event.time,
        "users": users,
        "reminders": reminders_t,
        "event_mode": event.event_mode,
    }"""

    def __init__(
        self,
        *,
        id: str,
        host: int,
        name: str,
        time: datetime,
        invites: list[discord.User],
        mode: str,
    ):
        self.id = id
        self.host = host
        self.name = name
        self.time = time
        self.invites = invites
        self.mode = mode

    def __repr__(self):
        return f"<Event(id={self.id}, host={self.host}, name={self.name}, time={self.time}, invites={self.invites}, mode={self.mode})>"


class Confirmation:
    def __init__(self, *, event_id: str, guest: int, confirmation: bool | None, reminders: list[int]):
        self.event_id = event_id
        self.guest = guest
        self.confirmation = confirmation
        self.reminders = reminders

    def __repr__(self):
        return f"<Confirmation(event_id={self.event_id}, guest={self.guest}, confirmation={self.confirmation}, reminders={self.reminders})>"
