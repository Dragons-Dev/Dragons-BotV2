import discord
import json
import os
from discord.ext import commands

from utils import Bot, CustomLogger, is_team

blacklist = ["extensions_commands", "internal", "__pycache__"]

def folder(ctx: discord.AutocompleteContext) -> list[str]:
    folders = [name for name in os.listdir("./extensions") if os.path.isdir(f"./extensions/{name}")]
    for bl in blacklist:
        if bl in folders:
            folders.remove(bl)
    return folders


def extension(ctx: discord.AutocompleteContext) -> list[str]:
    folder: str | None = ctx.options.items().mapping["folder"]
    if folder is None:
        return ["Please select a folder first"]
    path = f"extensions/{folder}"
    try:
        onlyfiles = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    except OSError:
        onlyfiles = []
    files = []
    for file in onlyfiles:
        files.append(file.replace(".py", ""))
    for bl in blacklist:
        if bl in files:
            files.remove(bl)
    return files


class ExtensionsCommands(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @commands.slash_command(name="activate_extension", description="Activate a selected Extension")
    @discord.option(autocomplete=folder, name="folder", description="Select the Folder", required=True)
    @discord.option(
        autocomplete=extension, name="extension", description="Select the Extension to activate", required=True
    )
    @commands.is_owner()
    async def activate_extension(self, ctx: discord.ApplicationContext, folder: str, extension: str):
        if folder in blacklist or extension in blacklist:
            return await ctx.response.send_message(
                f"The selected extension doesn't exist", ephemeral=True, delete_after=5
            )
        path: str = f"extensions.{folder}.{extension}"
        with open("./assets/disabled.json") as f:
            extension_store = json.load(f)

        if path not in extension_store:
            return await ctx.response.send_message(
                f"The selected extension {path} doesn't exist", ephemeral=True, delete_after=5
            )

        extension_store[path] = True
        with open("./assets/disabled.json", "w") as f:
            json.dump(extension_store, f, indent=4)

        self.logger.info(f"Extension {path} has been enabled and will be active after restart.")
        await ctx.response.send_message(
            f"✅ `{path}` has been marked as activated and will be active after restart.", ephemeral=True, delete_after=5
        )

    @commands.slash_command(name="deactivate_extension", description="Deactivate a selected Extension")
    @discord.option(autocomplete=folder, name="folder", description="Select the Folder", required=True)
    @discord.option(
        autocomplete=extension, name="extension", description="Select the Extension to deactivate", required=True
    )
    @commands.is_owner()
    async def deactivate_extension(self, ctx: discord.ApplicationContext, folder: str, extension: str):
        if folder in blacklist or extension in blacklist:
            return await ctx.response.send_message(
                f"The selected extension doesn't exist", ephemeral=True, delete_after=5
            )
        path: str = f"extensions.{folder}.{extension}"
        path = path.replace(".py", "")
        with open("./assets/disabled.json") as f:
            extension_store = json.load(f)

        if path not in extension_store:
            return await ctx.response.send_message(
                f"The selected extension {path} doesn't exist", ephemeral=True, delete_after=5
            )

        extension_store[path] = False
        with open("./assets/disabled.json", "w") as f:
            json.dump(extension_store, f, indent=4)

        
        self.logger.info(f"Extension: {path} has been disabled and will not be loaded on the next restart.")
        await ctx.response.send_message(
            f"🚫 `{folder}.{extension}` has been marked as deactivated and will not be loaded in the next restart.", ephemeral=True, delete_after=5
        )


def setup(client):
    client.add_cog(ExtensionsCommands(client))
