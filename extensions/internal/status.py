from asyncio import sleep

import discord
from discord.ext import commands, tasks

import pycord.multicog as pycog

from utils import Bot, BotActivity, CustomLogger, checks

status_emojis = {
    discord.Status.online: "🟢",
    discord.Status.idle: "🟡",
    discord.Status.dnd: "🔴",
    discord.Status.do_not_disturb: "🔴",
    discord.Status.invisible: "⚫",
    discord.Status.offline: "⚫",
    discord.Status.streaming: "🟣",
}

class InputModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(
            discord.ui.InputText(
                label="Activity Text",
                placeholder="Enter the activity text here...",
            ),
            *args,
            **kwargs,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

class StatusBuilder(discord.ui.View):
    def __init__(self, client: Bot):
        super().__init__()
        self.disable_on_timeout = True
        self.timeout = 120
        self.client = client
        self.activity_name = None
        self.activity_type = None
        self.status = None
        self.preview = None

    def _set_button_style(self, button: discord.ui.Button):
        self._unlock_submit()
        for _button in self.children:
            if _button.row == button.row:
                if _button != button:
                    _button.style = discord.ButtonStyle.primary
                    button.style = discord.ButtonStyle.success

    def _unlock_submit(self):
        if self.status and self.activity_name and self.activity_type:
            for button in self.children:
                button.disabled = False

    def _generate_preview(self):
        if not self.activity_name or not self.activity_type or not self.status:
            self.preview = f"Please select a status, activity type and enter the activity name."
        elif self.activity_type == discord.ActivityType.custom:
            self.preview = f"{status_emojis[self.status]} - {self.activity_name}"
        elif self.activity_type == discord.ActivityType.playing:
            self.preview = f"{status_emojis[self.status]} - Playing {self.activity_name}"
        elif self.activity_type == discord.ActivityType.listening:
            self.preview = f"{status_emojis[self.status]} - Listening to {self.activity_name}"
        elif self.activity_type == discord.ActivityType.watching:
            self.preview = f"{status_emojis[self.status]} - Watching {self.activity_name}"
        else:
            self.preview = f"{status_emojis[self.status]} - {self.activity_name} {self.activity_type}"

    @discord.ui.button(label="Watching", style=discord.ButtonStyle.primary, emoji="👀", row=0)
    async def watching(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.activity_type = discord.ActivityType.watching
        self._set_button_style(button)
        self._generate_preview()
        await interaction.edit(content=self.preview, view=self)

    @discord.ui.button(label="Listening", style=discord.ButtonStyle.primary, emoji="👂", row=0)
    async def listening(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.activity_type = discord.ActivityType.listening
        self._set_button_style(button)
        self._generate_preview()
        await interaction.edit(content=self.preview, view=self)

    @discord.ui.button(label="Playing", style=discord.ButtonStyle.primary, emoji="🎮", row=0)
    async def playing(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.activity_type = discord.ActivityType.playing
        self._set_button_style(button)
        self._generate_preview()
        await interaction.edit(content=self.preview, view=self)

    @discord.ui.button(label="Custom", style=discord.ButtonStyle.primary, emoji="🖊️", row=0)
    async def custom(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.activity_type = discord.ActivityType.custom
        self._set_button_style(button)
        self._generate_preview()
        await interaction.edit(content=self.preview, view=self)

    @discord.ui.button(label="Online", style=discord.ButtonStyle.primary, emoji="🟢", row=1)
    async def online(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.status = discord.Status.online
        self._set_button_style(button)
        self._generate_preview()
        await interaction.edit(content=self.preview, view=self)

    @discord.ui.button(label="AFK", style=discord.ButtonStyle.primary, emoji="🟡", row=1)
    async def afk(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.status = discord.Status.idle
        self._set_button_style(button)
        self._generate_preview()
        await interaction.edit(content=self.preview, view=self)

    @discord.ui.button(label="DnD", style=discord.ButtonStyle.primary, emoji="🔴", row=1)
    async def dnd(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.status = discord.Status.dnd
        self._set_button_style(button)
        self._generate_preview()
        await interaction.edit(content=self.preview, view=self)

    @discord.ui.button(label="Offline", style=discord.ButtonStyle.primary, emoji="⚫", row=1)
    async def offline(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.status = discord.Status.invisible
        self._set_button_style(button)
        self._generate_preview()
        await interaction.edit(content=self.preview, view=self)

    @discord.ui.button(label="Set Text", style=discord.ButtonStyle.primary, row=2)
    async def set_text(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = InputModal(title="Set the activity name")
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.activity_name = modal.children[0].value
        self._unlock_submit()
        self._generate_preview()
        await interaction.edit(content=self.preview, view=self)

    @discord.ui.button(label="Set Status", style=discord.ButtonStyle.success, emoji="✅", row=3, disabled=True)
    async def submit(self, button: discord.ui.Button, interaction: discord.Interaction):
        print(self.activity_name, self.activity_type, self.status)
        self._generate_preview()
        await interaction.edit(content=self.preview, view=None)
        if self.activity_type == discord.ActivityType.custom:
            await self.client.change_presence(activity=discord.CustomActivity(
                name=self.activity_name,
                state=self.activity_name,
            ), status=self.status)
        else:
            await self.client.change_presence(activity=discord.Activity(
                name=self.activity_name,
                type=self.activity_type,
            ), status=self.status)

class BotStatus(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.statuses: list[BotActivity] = [
            BotActivity(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="you",
                ),
                status=discord.Status.idle,
            ),
            BotActivity(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name="your commands",
                ),
                status=discord.Status.do_not_disturb,
            ),
            BotActivity(
                activity=discord.Activity(
                    type=discord.ActivityType.playing,
                    name="in a test environment!",
                ),
                status=discord.Status.online,
            ),
        ]


    @commands.Cog.listener("on_boot_done")
    async def on_boot_done(self):
        self.start_status._seconds = 30 * len(self.statuses)
        self.start_status.start()
        # set the execution loop to 30 (seconds) times the amount of statuses and start it

    @tasks.loop()
    async def start_status(self):
        for status in self.statuses:
            await self.client.change_presence(
                activity=status.activity,
                status=status.status,
            )
            await sleep(30)


    @pycog.subcommand("status")
    @commands.slash_command(name="set", description="[Bot Owner] Set's the status of the bot")
    @commands.is_owner()
    async def set_status(self, ctx: discord.ApplicationContext):
        await ctx.response.send_message(
            "This needs to be implemented...",
            ephemeral=True,
            view=StatusBuilder(self.client)
        )
        # TODO: Add views to set a status until next reboot
        # TODO: add database attachment to save persistent
        # TODO: ^ this needs a new enum for db, maybe use discords...

    @pycog.subcommand("status")
    @commands.slash_command(name="cycle", description="[Bot Owner] Toggles if the bot should cycle through the statuses.")
    async def cycle_status(self, ctx: discord.ApplicationContext):
        if not self.client.is_owner(ctx.author):
            await ctx.response.send_message(
                "You can't execute this command since you're not the owner.",
                ephemeral=True,
            )
        if self.start_status.is_running():
            self.start_status.stop()
            await ctx.response.send_message("Stopped cycling through statuses.", ephemeral=True)
        else:
            self.start_status.start()
            await ctx.response.send_message("Started cycling through statuses.", ephemeral=True)


def setup(client):
    client.add_cog(BotStatus(client))
