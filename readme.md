<p align="center">
    <a href="https://discord.gg/naweGHs9C7"><img src="https://img.shields.io/discord/578446945425555464?logo=discord&logoColor=%235865F2&label=Discord" alt="Discord server invite" /></a>
    <a href="https://github.com/Dragons-Dev/Dragons-BotV2/graphs/contributors"><img src="https://img.shields.io/github/contributors/Dragons-Dev/Dragons-BotV2"></img></a>
    <a href="https://github.com/Dragons-Dev/Dragons-BotV2/releases"><img src="https://img.shields.io/github/v/release/Dragons-Dev/Dragons-BotV2"></img></a>
    <a href="https://github.com/Dragons-Dev/Dragons-BotV2/commits"><img src="https://img.shields.io/github/commits-since/Dragons-Dev/Dragons-BotV2/latest" alt="Commit activity" /></a>
    <a href="https://github.com/Dragons-Dev/Dragons-BotV2/actions"><img src="https://github.com/Dragons-Dev/Dragons-BotV2/actions/workflows/github-code-scanning/codeql/badge.svg"></img></a>
    <a href="https://www.codefactor.io/repository/github/dragons-dev/dragons-botv2"><img src="https://www.codefactor.io/repository/github/dragons-dev/dragons-botv2/badge" alt="CodeFactor" /></a>
</p>


# Dragons Bot
A Discord multipurpose bot written in Python with many (yet to make) features.
It will have many different features, including a dashboard.
## What's coming?
- You can find future features and development progress in the Projects tab
## Prerequisites:
### API Keys
- [Discord](https://discord.com/developers/applications)
- [Google Cloud Key](https://console.cloud.google.com/apis/api/safebrowsing.googleapis.com)\
Keys have to be added into the config.py
```py
# config.py
DISCORD_API_KEY = ""
# The token you get from discord for authorizing your bot. https://discord.com/developers/applications

GOOGLE_API_KEY = ""
# An optional value required to scan for harmful urls in messages
# you'll have to create a project at googles cloud services and then add the safebrowsing api to it.
# after that you'll get an api key to use it
# https://console.cloud.google.com/apis/api/safebrowsing.googleapis.com

DEBUG_GUILDS: list[int] = []
# A debug guild. this is an optional value but if it's unset some features like modmail are not possible to use.
# commands can take up to one hour to sync. most times it's taking ~2-3 minuets to sync and maybe a client restart.

log_level = DEBUG
# depending on the set value there are
# logged   possible values are DEBUG; INFO; WARNING; ERROR; CRITICAL

IPC_SECRET = ""
# this secret will be used to encrypt the communication between the bot and webinterface
```
### Python
Download Python version from 3.11 from [python.org](https://www.python.org/downloads/release/python-3117/)
### pip packages
``pip install -r requirements.txt``
