from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import os


LOG_LEVEL_PARSER = {
    "debug": DEBUG,
    "info": INFO,
    "warning": WARNING,
    "error": ERROR,
    "critical": CRITICAL,
}


load_dotenv(dotenv_path=".env")

DISCORD_API_KEY = os.getenv("DISCORD_API_KEY", "")
# The token you get from discord for authorizing your bot. https://discord.com/developers/applications

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/content.sqlite")
# The database you want to utilize. Check out https://www.sqlalchemy.org/ for more information

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
# An api key from Google, this is required in order to scan for harmful urls
# https://console.cloud.google.com/apis/api/safebrowsing.googleapis.com/metrics?project=mails-366518

DEBUG_GUILDS: list[int] = []
# A debug guild. this is an optional value. this increases the time in which the commands show up after updating, but it
# will lead to commands not showing up in dm's which disables some features

log_level = LOG_LEVEL_PARSER.get(os.getenv("log_level", "INFO").lower(), INFO)
# the log level. this bot has built in logging. by modifying this value with one from the first import you change what's
# logged
discord_log_level = LOG_LEVEL_PARSER.get(os.getenv("discord_log_level", "INFO").lower(), WARNING)
# the log level for discord. Lowering this may lead to huge logs.

IPC_SECRET = os.getenv("IPC_SECRET", "")
# this secret will be used to encrypt the communication between the bot and webinterface

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
# get from https://developer.spotify.com/dashboard/

SERVER_TZ = ZoneInfo(os.getenv("SERVER_TZ", "UTC"))
