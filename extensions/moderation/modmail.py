import discord
from discord.ext import commands

from utils import Bot, CustomLogger


class EndModmailView(discord.ui.View):
    # class is displayed if the user runs the command `create_modmail` while having already an open modmail
    def __init__(self, author: discord.User, client: Bot):
        self.author = author
        self.client = client
        super().__init__(timeout=30, disable_on_timeout=True)

    @discord.ui.button(
        label="End Modmail",
        style=discord.ButtonStyle.blurple,
    )
    async def end_modmail(self, button: discord.ui.Button, interaction: discord.Interaction):
        _, guild_id = await self.client.db.get_modmail_link(self.author)
        guild = self.client.get_guild(guild_id)
        if guild is None:
            guild = await self.client.fetch_guild(guild_id)
        await self.client.db.remove_modmail_link(self.author)

        button.label = "Stopped Modmailing"
        button.disabled = (True,)
        button.style = discord.ButtonStyle.success
        await interaction.edit(
            content=f"You've stopped mailing with **{guild.name}**!\n"
                    f"## -# _Please note that the guild moderators can reopen modmails!_",
            view=self,
        )


class GuildSelectDropdown(discord.ui.Select):
    # select to show mutual guilds of the bot and the author
    def __init__(self, client_: Bot, author: discord.User):
        self.client = client_
        self.author = author
        options = [discord.SelectOption(label=guild.name, value=str(guild.id)) for guild in author.mutual_guilds]
        super().__init__(
            placeholder="Choose the guild to modmail with!",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        response = int(self.values[0])
        link = await self.client.db.get_modmail_link(self.author)
        if link:
            response = link[1]
        guild = self.client.get_guild(response)
        if guild is None:
            guild = await self.client.fetch_guild(response)
        if link:
            view = EndModmailView(self.author, self.client)
            await interaction.response.send_message(f"You are still chatting with **{guild.name}**", view=view)
        else:
            await self.client.db.add_modmail_link(self.author, guild)
            await interaction.response.send_message(f"You are now chatting with **{guild.name}**!", ephemeral=True)


class GuildSelectView(discord.ui.View):
    # View class to display the advanced Select `GuildSelectDropdown`
    def __init__(self, client: Bot, author: discord.User):
        super().__init__()
        self.add_item(GuildSelectDropdown(client, author))


class ModMail(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    def _to_embed(self, msg: discord.Message):
        pass

    @commands.slash_command(
        name="create_modmail",
        description="Start a new modmail chat.",
        contexts={
            discord.InteractionContextType.guild,
            discord.InteractionContextType.bot_dm,
            discord.InteractionContextType.private_channel,
        },
    )
    async def create_modmail(self, ctx: discord.ApplicationContext):
        _, guild_id = await self.client.db.get_modmail_link(ctx.author)
        if ctx.guild:  # if the command is run inside a guild
            if guild_id:  # if any guild id is in the database
                if ctx.guild.id == guild_id:  # if the guild id the command is run is the same as in the database
                    view = EndModmailView(ctx.author, self.client)
                    return await ctx.response.send_message(
                        f"You are still chatting with this guild!", view=view, ephemeral=True
                    )

            else:  # if no id is in the database for this user, a modmail with this guild will be created
                await self.client.db.add_modmail_link(ctx.author, ctx.guild)
                return await ctx.response.send_message(
                    "A new modmail will be created. Please check your DM's", ephemeral=True
                )

        elif (
                guild_id
        ):  # if the command is run outside a guild but with an id in the database the user will be shown the `EndModmailView`
            view = EndModmailView(ctx.author, self.client)
            guild = self.client.get_guild(guild_id)
            if guild is None:
                guild = await self.client.fetch_guild(guild_id)
            return await ctx.response.send_message(f"You are still chatting with **{guild.name}**!", view=view)

        else:  # if the command is run outside a guild and no id is in the db, provide `GuildSelectView`
            view = GuildSelectView(self.client, ctx.author)
            return await ctx.response.send_message(
                "With which guild do you want to modmail?", ephemeral=True, view=view
            )

    @commands.Cog.listener("on_message")
    async def on_modmail(self, msg: discord.Message):
        if msg.author.bot:
            return
        if msg.guild:
            return


def setup(client: Bot):
    client.add_cog(ModMail(client))
