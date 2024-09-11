import datetime
import uuid as _uuid

import chat_exporter
import discord
from discord.ext import commands
from discord.utils import escape_markdown, get_or_fetch

from utils import Bot, ButtonConfirm, CustomLogger, SettingsEnum


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
        _, guild_id, _, _ = await self.client.db.get_modmail_link(self.author)
        guild = self.client.get_guild(guild_id)
        if guild is None:
            guild = await self.client.fetch_guild(guild_id)
        await self.client.db.remove_modmail_link(self.author)

        button.label = "Stopped Modmailing"
        button.disabled = (True,)
        button.style = discord.ButtonStyle.success
        await interaction.edit(
            content=f"You've stopped mailing with **{escape_markdown(guild.name)}**!\n"
            f"## -# _Please note that the guild moderators can reopen modmails!_",
            view=self,
        )


class GuildSelectDropdown(discord.ui.Select):
    # select to show mutual guilds of the bot and the author
    def __init__(self, client_: Bot, author: discord.User, anonymous: bool):
        self.client = client_
        self.author = author
        self.anon = anonymous
        options = [discord.SelectOption(label=guild.name, value=str(guild.id)) for guild in author.mutual_guilds]
        super().__init__(
            placeholder="Choose the guild to modmail with!",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        response = int(self.values[0])
        _, guild_id, _, _ = await self.client.db.get_modmail_link(self.author)
        if guild_id:
            response = guild_id
        guild = self.client.get_guild(response)
        if guild is None:
            guild = await self.client.fetch_guild(response)
        if guild_id:
            view = EndModmailView(self.author, self.client)
            await interaction.response.send_message(
                f"You are still chatting with **{escape_markdown(guild.name)}**", view=view
            )
        else:
            uuid = _uuid.uuid4()
            await self.client.db.add_modmail_link(self.author, guild, str(uuid), self.anon)
            await interaction.response.send_message(
                f"You are now chatting with **{escape_markdown(guild.name)}**!", ephemeral=True
            )


class GuildSelectView(discord.ui.View):
    # View class to display the advanced Select `GuildSelectDropdown`
    def __init__(self, client: Bot, author: discord.User, anonymous: bool):
        super().__init__(timeout=30, disable_on_timeout=True)
        self.add_item(GuildSelectDropdown(client, author, anonymous))


def _first_int(uuid: str):
    """
    Converts an uuid to an integer which is less than 5
    Args:
        uuid: A UUID
    Returns:
        An ``integer`` 5 <=
    """
    for x in uuid:
        if x.isdigit():
            num = int(x)
            if num > 5:
                return num // 2
            else:
                return num


def _to_embed(msg: discord.Message, uuid: str, anonymous: bool):
    """
    Converts a ``discord.Message`` object to a ``discord.Embed`` object.
    Args:
        msg: the ``discord.Message`` object to convert.
        uuid: the ``uuid`` of the user
        anonymous: if the user wants to be anonymous, changes avatar and username so you can't know who is writing with you

    Returns:
        A ``discord.Embed`` object with the user, the original message and a footer containing the original timestamp of the message and either an uuid or discord id of the user.
    """
    if anonymous:
        num = _first_int(uuid)
        icon_url = f"https://cdn.discordapp.com/embed/avatars/{num}.png"
        author = discord.EmbedAuthor(name=f"Anon#{uuid[:7]}", icon_url=icon_url)
        footer = discord.EmbedFooter(text=f"UUID: {uuid}")
    else:
        author = discord.EmbedAuthor(
            name=msg.author.name,
            url=f"https://discord.id/?prefill={msg.author.id}",
            icon_url=msg.author.display_avatar.url,
        )
        footer = discord.EmbedFooter(text=f"Member ID: {msg.author.id}")

    return discord.Embed(
        author=author,
        color=discord.Color.dark_magenta(),
        description=msg.content,
        footer=footer,
        timestamp=msg.created_at,
    )


class ModMail(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    modmail_group = discord.SlashCommandGroup(
        "modmail",
        contexts={
            discord.InteractionContextType.guild,
            discord.InteractionContextType.bot_dm,
            discord.InteractionContextType.private_channel,
        },
    )

    @modmail_group.command(name="create", description="Start a new modmail chat.")
    @discord.commands.option(
        name="anonymous", description="Do you want to be anonymous in this modmail?", input_type=bool, default=False
    )
    async def create_modmail(self, ctx: discord.ApplicationContext, anonymous: bool):
        _, guild_id, _, _ = await self.client.db.get_modmail_link(ctx.author)
        if ctx.guild:  # if the command is run inside a guild
            if guild_id:  # if any guild id is in the database
                guild: discord.Guild = await get_or_fetch(self.client, "guild", guild_id, default=None)
                if ctx.guild.id == guild_id:  # if the guild id the command is run is the same as in the database
                    view = EndModmailView(ctx.author, self.client)
                    return await ctx.response.send_message(
                        f"You are still chatting with this guild!", view=view, ephemeral=True
                    )

                else:
                    view = EndModmailView(ctx.author, self.client)
                    return await ctx.response.send_message(
                        f"You are still chatting with **{escape_markdown(guild.name)}**!", view=view, ephemeral=True
                    )

            else:  # if no id is in the database for this user, a modmail with this guild will be created
                uuid = str(_uuid.uuid4())
                await self.client.db.add_modmail_link(ctx.author, ctx.guild, uuid, anonymous)
                return await ctx.response.send_message(
                    "A new modmail will be created. Please check your DM's", ephemeral=True
                )

        elif (
            guild_id
        ):  # if the command is run outside a guild but with an id in the database the user will be shown the `EndModmailView`
            view = EndModmailView(ctx.author, self.client)
            guild: discord.Guild = await get_or_fetch(self.client, "guild", guild_id, default=None)  # type: ignore
            return await ctx.response.send_message(
                f"You are still chatting with **{escape_markdown(guild.name)}**!", view=view, ephemeral=True
            )

        else:  # if the command is run outside a guild and no id is in the db, provide `GuildSelectView`
            view = GuildSelectView(self.client, ctx.author, anonymous)
            return await ctx.response.send_message(
                "With which guild do you want to modmail?", ephemeral=True, view=view
            )

    @modmail_group.command(name="end", description="Stop a modmail chat.")
    async def end_modmail(self, ctx: discord.ApplicationContext):
        user_id, guild_id, uuid, anon = await self.client.db.get_modmail_link(ctx.author)
        guild: discord.Guild = await get_or_fetch(self.client, "guild", guild_id, default=None)
        view = ButtonConfirm(cancel_title=f"You continue to mail with **{escape_markdown(guild.name)}**!")
        msg = await ctx.response.send_message(
            f"Do you really want to stop mailing with **{escape_markdown(guild.name)}**!", view=view, ephemeral=True
        )
        view.original_msg = msg
        await view.wait()
        if view.value is None or not view.value:
            return
        else:
            await self.client.db.remove_modmail_link(ctx.author)
            await ctx.followup.send(
                f"You've stopped mailing with **{escape_markdown(guild.name)}**!\n"
                f"## -# _Please note that the guild moderators can reopen modmails!_",
                ephemeral=True,
            )
            modmail_channel_id = await self.client.db.get_setting(SettingsEnum.ModmailChannel, guild)
            modmail_channel: discord.TextChannel = await get_or_fetch(
                guild, "channel", modmail_channel_id, default=None
            )
            for thread in modmail_channel.threads:
                if (
                    (f"Thread for {ctx.author.name}" == thread.name or f"Thread for Anon#{uuid[:7]}" == thread.name)
                    and not thread.archived
                    and not thread.locked
                ):
                    await thread.send(
                        (f"Anon#{uuid[:7]}" if anon else escape_markdown(ctx.author.name))
                        + " has closed the conversation!"
                    )
                    await thread.edit(locked=True)
                    return
            else:
                pass

    @commands.Cog.listener("on_message")
    async def on_modmail(self, msg: discord.Message):
        if msg.author.bot:
            return
        user_id, guild_id, uuid, anonymous = await self.client.db.get_modmail_link(msg.author)
        if msg.guild:
            if msg.channel.type == discord.ChannelType.public_thread:
                if msg.channel.name.startswith("Thread for"):
                    # convert all attachments to files to send them to the user
                    files = []
                    for attachment in msg.attachments:
                        if attachment.size >= 10000000:  # 10 MB
                            return await msg.channel.send(
                                f"## Error\n"
                                f"Your file ("
                                f"{escape_markdown(attachment.filename)}"
                                f") is to large to be send!\n"
                                f"Maximum to be sent are 10MB"
                            )
                        file = await attachment.to_file()
                        files.append(file)

                    user_name = msg.channel.name.strip("Thread for").strip()
                    async for message in msg.channel.history():
                        if message.author.id == self.client.user.id:
                            if message.embeds:
                                footer = message.embeds[0].footer.text
                                break
                    if user_name.startswith("Anon#"):
                        recipient_uuid = footer.strip("UUID:").strip()
                        recipient_id, _, _, _ = await self.client.db.get_modmail_link(uuid=recipient_uuid)
                        recipient: discord.Member = await get_or_fetch(msg.guild, "member", recipient_id, default=None)
                        if not recipient:
                            return msg.channel.send("Member not found!")
                        else:
                            await recipient.send(
                                embed=discord.Embed(
                                    author=discord.EmbedAuthor(
                                        name=msg.author.name, icon_url=msg.author.display_avatar.url
                                    ),
                                    color=discord.Color.dark_magenta(),
                                    description=msg.content,
                                    footer=discord.EmbedFooter(text=f"Member ID: {msg.author.id}"),
                                    timestamp=msg.created_at,
                                ),
                                files=(None if len(files) == 0 else files),
                            )
                    else:
                        recipient_id = footer.strip("Member ID:").strip()
                        recipient: discord.Member = await get_or_fetch(  # type: ignore
                            msg.guild, "member", int(recipient_id), default=None
                        )
                        if not recipient:
                            return msg.channel.send("Member not found!")
                        else:
                            await recipient.send(
                                embed=discord.Embed(
                                    author=discord.EmbedAuthor(
                                        name=msg.author.name, icon_url=msg.author.display_avatar.url
                                    ),
                                    color=discord.Color.dark_magenta(),
                                    description=msg.content,
                                    footer=discord.EmbedFooter(text=f"Member ID: {msg.author.id}"),
                                    timestamp=msg.created_at,
                                ),
                                files=(None if len(files) == 0 else files),
                            )

        # at this point it's made sure it was a dm to the bot in a modmail context
        guild = await get_or_fetch(self.client, "guild", guild_id, default=None)
        embed = _to_embed(msg, uuid, anonymous)
        # convert all attachments to files to send them in the modmail channel
        files = []
        for attachment in msg.attachments:
            if attachment.size >= 10000000:  # 10 MB
                return await msg.channel.send(
                    f"## Error\n"
                    f"Your file ("
                    f"{escape_markdown(attachment.filename)}"
                    f") is to large to be send!\n"
                    f"Maximum to be sent are 10MB"
                )
            file = await attachment.to_file()
            files.append(file)
        # get the modmail channel for the guild the user wants to mail with
        try:
            modmail_channel_id = await self.client.db.get_setting(SettingsEnum.ModmailChannel, guild)
        except AttributeError:
            return await msg.author.send(
                f"If you want to modmail with someone please use first {self.create_modmail.mention}"
            )
        # let the user know if the modmail channel is not set up
        if not modmail_channel_id:
            await msg.author.send(
                "This feature is not set up in the guild you are trying to chat with.\n"
                "-# You'll have to contact the mods or owner directly and let them enable this feature for you!",
                delete_after=20,
            )
        else:
            # get the channel object of the modmail channel
            modmail_channel: discord.TextChannel = await get_or_fetch(
                guild, "channel", modmail_channel_id, default=None
            )
            # iterate over all known threads if the user and the thread name match, if yes send the message and return
            for thread in modmail_channel.threads:
                if (
                    (f"Thread for {escape_markdown(embed.author.name)}" == thread.name)
                    and not thread.archived
                    and not thread.locked
                ):
                    await thread.send(embed=embed, files=(None if len(files) == 0 else files))
                    return
            # if no known thread matches, create a new thread and send the message
            else:
                title = f"Thread for {escape_markdown(embed.author.name)}"
                start_msg = await modmail_channel.send(f"Creating {escape_markdown(title)}")
                new_thread = await start_msg.create_thread(name=title, auto_archive_duration=4320)
                await new_thread.send(embed=embed, files=(None if len(files) == 0 else files))


def setup(client: Bot):
    client.add_cog(ModMail(client))
