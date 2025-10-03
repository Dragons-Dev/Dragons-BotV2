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
from logging import DEBUG, INFO, WARNING

DISCORD_API_KEY = ""
# The token you get from discord for authorizing your bot. https://discord.com/developers/applications

DATABASE_URL = "sqlite+aiosqlite:///data/content.sqlite"
# The database you want to utilize. Check out https://www.sqlalchemy.org/ for more information
# Default path is ./data/content.sqlite

GOOGLE_API_KEY = ""
# An api key from Google, this is required in order to scan for harmful urls
# https://console.cloud.google.com/apis/api/safebrowsing.googleapis.com

log_level = DEBUG
# the log level. this bot has built in logging. by modifying this value with one from the first import you change what's
# logged
discord_log_level = WARNING
# the log level for discord. Lowering this may lead to huge logs.

IPC_SECRET = "top_secret"
# this secret will be used to encrypt the communication between the bot and webinterface
```
### Python
Download Python version from 3.11 from [python.org](https://www.python.org/downloads/release/python-3117/)
### pip packages
``pip install -r requirements.txt``
