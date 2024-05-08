from logging import CRITICAL, DEBUG, ERROR, INFO, WARNING

from wavelink import Node

DISCORD_API_KEY = ""
# The token you get from discord for authorizing your bot. https://discord.com/developers/applications

GOOGLE_API_KEY = ""
# An api key from googe, this is required in order to scan for harmful urls
# https://console.cloud.google.com/apis/api/safebrowsing.googleapis.com/metrics?project=mails-366518

DEBUG_GUILDS: list[int] = []
# A debug guild. this is an optional value, but I recommend to set it if you use the bot private. this increases the
# time in which the commands show up after updating

log_level = DEBUG
# the log level. this bot has built in logging. by modifying this value with one from the first import you change what's
# logged

IPC_SECRET = ""
# this secret will be used to encrypt the communication between the bot and webinterface
