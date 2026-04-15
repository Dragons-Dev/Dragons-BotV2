import json
import logging
import os
import time
from datetime import datetime as dt
from sys import exit as exit_
from sys import stdout

import aiohttp
import discord
import psutil
from discord.ext import commands

import config
from config import DISCORD_API_KEY
from utils import Bot, ORMDataBase, ShortTermStorage, VersionInfo, rem_log
from utils.logger import CustomFormatter

bot = Bot(
    command_prefix=commands.when_mentioned,
    case_insensitive=True,
    strip_after_prefix=True,
    intents=discord.Intents.all(),
    activity=discord.CustomActivity(name="Booting...", state="Booting..."),
    status=discord.Status.dnd,
    version=VersionInfo(2, 2, 0, ""),
)


@bot.listen("on_ready", once=True)
async def on_boot():
    bot.sts = ShortTermStorage(path="data/sts.sqlite")
    await bot.sts.setup(bot.boot_time)
    bot.logger.debug("Initialized sts db")
    bot.db = ORMDataBase()
    await bot.db.setup(bot.boot_time)
    bot.logger.debug("Initialized content db")
    bot.api = aiohttp.ClientSession(
        "https://discord.com",
        headers={"Authorization": "Bot " + DISCORD_API_KEY, "User-Agent": f"Dragons BotV{bot.client_version}"},
    )
    resp = await bot.api.get("/api/v10/gateway/bot")
    data = await resp.json()
    rem_log()
    bot.logger.debug(f"Requested {resp.url}; Received {resp.status}")
    bot.logger.info(
        f"Bot started at {bot.boot_time.strftime('%H:%M:%S')} Boot took ~{(dt.now() - bot.boot_time).seconds}s"
    )
    bot.logger.info(
        f"""Session start limit {data["session_start_limit"]["remaining"]} | Resets at {
            dt.fromtimestamp(time.time() + (int(data["session_start_limit"]["reset_after"]) / 1000)).strftime(
                "%d.%m.%Y %H:%M:%S"
            )
        }"""
    )
    bot.logger.info(
        f"Name: {bot.user.name}#{bot.user.discriminator} | ID: {bot.user.id} | Latency: {round(bot.latency * 1000)}ms | "
        f"Version: {bot.client_version}"
    )
    bot.logger.info(f"It's on {len(bot.guilds)} servers")
    bot.dispatch("start_done")


if __name__ == "__main__":
    # get all relevant loggers and set their levels
    dc_logger = logging.getLogger("discord")
    dc_logger.setLevel(config.discord_log_level)
    console_handle = logging.StreamHandler(stdout)
    console_handle.setFormatter(CustomFormatter())
    console_handle.setLevel(config.discord_log_level)
    dc_logger.addHandler(console_handle)
    sqlalchemy_logger = logging.getLogger("sqlalchemy.engine")
    sqlalchemy_logger.setLevel(logging.WARNING)
    sqlalchemy_logger.addHandler(console_handle)

    with open("./assets/disabled.json") as f:
        extension_store = json.load(f)

    for root, dirs, files in os.walk("./extensions"):
        for file in files:
            if file.endswith(".py") and not file.startswith("_"):
                rel_path = os.path.relpath(os.path.join(root, file), ".")
                ext_name = rel_path.replace(os.sep, ".").removesuffix(".py")

                if ext_name not in extension_store:
                    extension_store[ext_name] = True

                if extension_store[ext_name]:
                    try:
                        bot.load_extension(ext_name)
                        bot.logger.info(f"{ext_name} loaded successfully!")
                    except Exception as e:
                        bot.logger.critical(f"{ext_name}: {str(e)}")  # raise errors and stop connecting to discord
                        exit_("Error loading extensions!")
                else:
                    bot.logger.warning(f"{ext_name} is disabled!")

    with open("./assets/disabled.json", "w") as f:
        json.dump(extension_store, f, indent=4)

    if DISCORD_API_KEY == "":
        bot.logger.critical("No token has been passed to the bot.")
        exit_(1)
    pid = os.getpid()
    try:
        bot.run(DISCORD_API_KEY)
    except KeyboardInterrupt:
        bot.logger.critical("Shutting down...")
    finally:
        psutil.Process(pid).terminate()
