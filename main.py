import json
import time
from datetime import datetime as dt
from sys import exit as exit_

import discord
import wavelink
from discord.ext import commands

from config import DEBUG_GUILDS, DISCORD_API_KEY
from utils import Bot, ContentDB, ShortTermStorage, rem_log

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
    await bot.db.setup(bot.boot_time)
    bot.sts = ShortTermStorage(path="data/sts.sqlite")
    await bot.sts.setup(bot.boot_time)
    resp = await bot.api.get("/api/v10/gateway/bot")
    data = await resp.json()
    await wavelink.Pool.connect(
        nodes=[
            wavelink.Node(
                identifier="Private Node",
                uri="http://85.215.133.202:2333",
                password="7HX8wDfOLDT0IVIpgz6mqnWHnqcnIXF9rvjFUqZM3oyyVWybBOiFvcfZyPBr",
            )
        ],
        client=bot,
        cache_capacity=1000,
    )
    rem_log()
    bot.logger.debug(f"Requested {resp.url}; Received {resp.status}")
    bot.logger.info(
        f"Bot started at {bot.boot_time.strftime('%H:%M:%S')} Boot took ~{(dt.now() - bot.boot_time).seconds}s"
    )
    bot.logger.info(
        f"""Session start limit {data['session_start_limit']['remaining']} | Resets at {dt.fromtimestamp(
            time.time() + (int(data['session_start_limit']['reset_after']) / 1000)).strftime('%d.%m.%Y %H:%M:%S')}"""
    )
    bot.logger.info(
        f"Name: {bot.user.name}#{bot.user.discriminator} | ID: {bot.user.id} | Latency: {round(bot.latency * 1000)}ms | "
        f"Version: {bot.client_version}"
    )
    bot.logger.info(f"It's on {len(bot.guilds)} servers")
    bot.dispatch("start_done")


if __name__ == "__main__":
    extensions = bot.load_extensions("extensions", recursive=True, store=True)  # load every extension
    with open("./assets/disabled.json") as f:
        extension_store = json.load(f)
    for extension, status in extensions.items():  # go through every extension and save not registered
        if extension not in extension_store:
            extension_store[extension] = True
        if status is True:
            if not extension_store[extension]:
                bot.unload_extension(extension)  # unload extensions marked with false in /assets/disabled.json
                bot.logger.warning(f"{extension} is disabled!")
            else:
                bot.logger.info(f"{extension} loaded successfully!")
        else:
            bot.logger.critical(f"{extension}: {str(status)}")  # raise errors and stop connecting to discord
            exit_("Error loading extensions!")
    with open("./assets/disabled.json", "w") as f:
        json.dump(extension_store, f, indent=4)
    if DISCORD_API_KEY == "":
        bot.logger.critical(f"No token has been passed to the bot.")
        exit_(1)
    if DEBUG_GUILDS is None or not DEBUG_GUILDS:
        bot.logger.warning("No Debug guild specified. Commands can take up to 1 hour to sync!")

    bot.run(DISCORD_API_KEY)
