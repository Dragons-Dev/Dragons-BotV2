import discord


class ButtonInfo(discord.ui.View):
    def __init__(self, text):
        if len(text) > 80:
            raise discord.ValidationError("Buttons text is limited to 80 characters")
        self.text = text
        super().__init__(timeout=0)

        self.add_item(discord.ui.Button(label=text, disabled=True, style=discord.ButtonStyle.red))
