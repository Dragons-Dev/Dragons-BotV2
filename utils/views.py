from datetime import datetime

import discord


class ButtonInfo(discord.ui.View):
    def __init__(self, text: str):
        if len(text) > 80:
            raise discord.ValidationError("Buttons text is limited to 80 characters")
        self.text = text
        super().__init__(timeout=0)

        self.add_item(discord.ui.Button(label=text, disabled=True, style=discord.ButtonStyle.red))


class ButtonConfirm(discord.ui.View):
    def __init__(self, cancel_title: str):
        super().__init__(timeout=120, disable_on_timeout=True)
        self.value: bool | None = None
        self.cancel_title: str = cancel_title
        self.original_msg: discord.Interaction | None = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(invisible=True)
        self.value = True
        self.disable_all_items()
        button.style = discord.ButtonStyle.blurple
        await self.original_msg.edit(view=self)  # type: ignore
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=discord.Embed(title=self.cancel_title, color=discord.Color.red(), timestamp=datetime.now()),
            ephemeral=True,
        )
        self.value = False
        self.disable_all_items()
        button.style = discord.ButtonStyle.blurple
        await self.original_msg.edit(view=self)  # type: ignore
        self.stop()
