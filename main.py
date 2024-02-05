import time
from datetime import datetime as dt
from sys import exit as exit_

import discord
from discord.ext import commands

from config import DEBUG_GUILDS, DISCORD_TOKEN
from utils import Bot, ContentDB, individual_users, rem_log

bot = Bot(
    command_prefix=commands.when_mentioned,
    case_insensitive=True,
    strip_after_prefix=True,
    intents=discord.Intents.all(),
    debug_guilds=DEBUG_GUILDS,
    activity=discord.CustomActivity(name="Booting...", state="Booting..."),
    status=discord.Status.dnd,
)


@bot.listen("on_ready", once=True)
async def on_boot():
    bot.db = ContentDB(path="data/content.sqlite")
    await bot.db.setup(bot.boot)
    resp = await bot.api.get("/api/v10/gateway/bot")
    data = await resp.json()
    rem_log()
    bot.logger.debug(f"Requested {resp.url}; Received {resp.status}")
    bot.logger.info(f"Bot started at {bot.boot.strftime('%H:%M:%S')} Boot took ~{(dt.now()-bot.boot).seconds}s")
    bot.logger.info(
        f"""Session start limit {data['session_start_limit']['remaining']} | Resets at {dt.fromtimestamp(
            time.time()+(int(data['session_start_limit']['reset_after'])/1000)).strftime('%d.%m.%Y %H:%M:%S')}"""
    )
    bot.logger.info(
        f"Name: {bot.user.name}#{bot.user.discriminator} | ID: {bot.user.id} | Latency: {round(bot.latency*1000)}ms"
    )
    bot.logger.info(
        f"It's on {len(bot.guilds)} guilds seeing {len(bot.users)} users from which {len(individual_users(bot.users))} "
        f"are individual."
    )
    bot.dispatch("start_done")


if __name__ == "__main__":
    extensions = bot.load_extensions("extensions", recursive=True, store=True)
    for extension, status in extensions.items():
        if status is True:
            bot.logger.info(f"{extension} loaded successfully!")
        else:
            bot.logger.critical(f"{extension}: {str(status)}")
            exit_("Error loading extensions!")
    bot.run(DISCORD_TOKEN)
