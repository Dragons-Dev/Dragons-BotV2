from discord import ApplicationCommandError
import discord
from datetime import datetime


class CommandDisabledError(ApplicationCommandError):
    pass


class InsufficientPermission(ApplicationCommandError):
    pass


class Event():
    """event_t = {
            "event_id": event.event_id,
            "host": event.host,
            "name": event.event_name,
            "time": event.time,
            "users": users,
            "reminders": reminders_t,
            "event_mode": event.event_mode,
        }"""
    def __init__(self, *, id: str, host: int, name: str, time: datetime, invites: list[discord.User], reminders: list[int], mode: str):
        self.id = id
        self.host = host
        self.name = name
        self.time = time
        self.invites = invites
        self.reminders = reminders
        self.mode = mode
    
    def __repr__(self):
        event_t = {
            "event_id": self.id,
            "host": self.host,
            "name": self.name,
            "time": self.time,
            "users": self.invites,
            "reminders":  self.reminders,
            "event_mode":  self.mode,
        }
        return str(event_t)