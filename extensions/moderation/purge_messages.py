import discord
from discord.ext import commands

from utils import Bot, CustomLogger, is_team


class MessagePurge(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @commands.slash_command(name="purge", description="Purge messages from a channel")
    @discord.option(
        "amount",
        description="The amount of messages to delete",
        default=100,
        min_value=1,
        max_value=100,
    )
    @discord.option(
        "which",
        description="Which messages to delete",
        required=False,
        input_type=discord.SlashCommandOptionType.mentionable,
    )
    @is_team()
    async def purge(
            self, ctx: discord.ApplicationContext, which: discord.User | discord.Role | None = None, amount: int = 100
    ):
        """
        Purges messages from a channel

        Args:
            ctx (discord.ApplicationContext): The context of the command
            which (discord.User | discord.Role): The user or role to delete messages from
            amount (int): The amount of messages to delete
        """
        if amount > 100:
            await ctx.response.send_message("You can only delete up to 100 messages at a time.", ephemeral=True)
            return
        await ctx.defer(ephemeral=True)
        if which is None:
            deleted_messages = await ctx.channel.purge(
                limit=amount, reason=f"{ctx.author.name} purged {ctx.channel.name}"
            )
        elif type(which) is discord.Role:
            deleted_messages = await ctx.channel.purge(
                limit=amount,
                check=lambda message: which.id in [r.id for r in message.author.roles],
                reason=f"{ctx.author.name} purged {ctx.channel.name}",
            )
        else:
            deleted_messages = await ctx.channel.purge(
                limit=amount,
                check=lambda message: message.author.id == which.id,
                reason=f"{ctx.author.name} purged {ctx.channel.name}",
            )
        await ctx.followup.send(f"Deleted {len(deleted_messages)} messages.", ephemeral=True)


def setup(client):
    client.add_cog(MessagePurge(client))
