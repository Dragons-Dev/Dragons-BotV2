import random
import string

import discord
from discord.ext import commands
from discord.utils import escape_markdown

from utils import Bot, CustomLogger


class PasswordSelector(discord.ui.Select):
    def __init__(self, length: int):
        self.length = length
        options = [
            discord.SelectOption(
                label="Upper-case Letters",
                description="Password will contain Upper-case letters.",
                value="uppercase"
            ),
            discord.SelectOption(
                label="Lower-case Letters",
                description="Password will contain lower-case letters.",
                value="lowercase"
            ),
            discord.SelectOption(
                label="Numbers",
                description="Password will contain numbers.",
                value="numbers"
            ),
            discord.SelectOption(
                label="Punctuation",
                description="Password will contain punctuation.",
                value="punctuation"
            ),
        ]
        super().__init__(
            options=options,
            min_values=1,
            max_values=4,
            placeholder="Select all elements you password should contain!"
        )

    async def callback(self, interaction: discord.Interaction):
        choices = []
        if "uppercase" in self.values:
            choices.append(string.ascii_uppercase)
        if "lowercase" in self.values:
            choices.append(string.ascii_lowercase)
        if "numbers" in self.values:
            choices.append(string.digits)
        if "punctuation" in self.values:
            choices.append(string.punctuation)
        choices = ''.join(choices)  # type: ignore
        pw = ''.join(random.choice(choices) for _ in range(self.length))
        await interaction.response.send_message(escape_markdown(pw), ephemeral=True)
        await interaction.delete_original_response()


class PasswordView(discord.ui.View):
    def __init__(self, length):
        self.length = length
        super().__init__()
        self.disable_on_timeout = True
        self.timeout = 5
        self.add_item(PasswordSelector(length=self.length))


class PasswordGenerator(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @commands.slash_command(
        name="generate_password",
        description="Generate a random password.",
        contexts={
            discord.InteractionContextType.guild,
            discord.InteractionContextType.bot_dm,
            discord.InteractionContextType.private_channel
        }
    )
    @discord.option(
        name="password length",
        default=16,
        required=False,
        input_type=int,
        max_value=1024,
        description="The length of the generated password.",
    )
    async def generate_password(self, ctx: discord.ApplicationContext, length: int):
        view = PasswordView(length=length)
        await ctx.response.send_message(
            "Please select all elements you password should contain!",
            ephemeral=True,
            view = view
        )


def setup(client):
    client.add_cog(PasswordGenerator(client))
