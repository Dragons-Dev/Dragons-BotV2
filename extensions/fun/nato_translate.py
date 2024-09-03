import io

import discord
from discord.ext import commands

from utils import Bot, CustomLogger

nato_alphabet = {
    "a": "ALPHA",
    "b": "BRAVO",
    "c": "CHARLIE",
    "d": "DELTA",
    "e": "ECHO",
    "f": "FOXTROT",
    "g": "GOLF",
    "h": "HOTEL",
    "i": "INDIA",
    "j": "JULIET",
    "k": "KILO",
    "l": "LIMA",
    "m": "MIKE",
    "n": "NOVEMBER",
    "o": "OSCAR",
    "p": "PAPA",
    "q": "QUEBEC",
    "r": "ROMEO",
    "s": "SIERRA",
    "t": "TANGO",
    "u": "UNIFORM",
    "v": "VICTOR",
    "w": "WHISKEY",
    "x": "XRAY",
    "y": "YANKEE",
    "z": "ZULU",
    "ä": "ALPHA-ECHO",
    "ö": "OSCAR-ECHO",
    "ü": "UNIFORM-ECHO",
}


class NatoTranslator(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @commands.slash_command(
        name="nato-translator",
        description="Translates an input into the Nato alphabet",
        contexts={
            discord.InteractionContextType.guild,
            discord.InteractionContextType.bot_dm,
            discord.InteractionContextType.private_channel,
        },
    )
    async def nato_translator(
        self,
        ctx: discord.ApplicationContext,
        input: discord.Option(  # type: ignore
            input_type=str, name="input", description="The word or sentence you want to translate into Nato Alphabet."
        ),
    ):
        """
        Takes an input from the command and translates every single letter to the nato alphabet. Ignores numbers and
        unknown characters. If the output is longer than 2000 Characters long it's sent back as a file else as embed.
        """
        output = []
        for letter in input:
            try:
                if letter.isdigit():
                    output.append(letter)
                elif letter == " ":
                    output.append("|")
                else:
                    output.append(nato_alphabet[letter.lower()])
            except:
                self.logger.warning(f"{letter} is not supported in NATO ALPHABET")
        out = " ".join(output)
        em = discord.Embed(description=out)
        if not len(em) > 2000:
            await ctx.response.send_message("There you go!", embed=em, ephemeral=True)
        else:
            temp = io.StringIO(out)
            file = discord.File(fp=temp, filename="output.txt")
            await ctx.response.send_message("There you go!", file=file, ephemeral=True)
            temp.close()


def setup(client):
    client.add_cog(NatoTranslator(client))
