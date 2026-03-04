from datetime import datetime

import discord


class ButtonInfo(discord.ui.View):
    def __init__(self, text):
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


class PaginationButton(discord.ui.Button):
    def __init__(self, label: str, *, new_page: int, discord_id: int | None = None, disabled: bool = False):
        """
        A button that changes the page of a ContainerPaginator when clicked.
        :param label: The buttons label
        :param new_page: the page the paginator should switch to when this button is clicked
        :param discord_id: a unique identifier for this button, required if you want to disable/enable it later.
        :param disabled: if the button should be disabled (e.g. on the next button on the last page)
        """
        super().__init__(
            label=label,
            style=(discord.ButtonStyle.blurple if not disabled else discord.ButtonStyle.gray),
            id=discord_id,
            disabled=disabled,
        )
        self.new_page = new_page

    async def callback(self, interaction: discord.Interaction):
        view: ContainerPaginator = self.view  # type: ignore
        view.set_page(self.new_page)
        await interaction.response.edit_message(view=view.update_view())


class PageSelectModal(discord.ui.Modal):
    def __init__(self, trigger_view):
        """
        This modal is triggered by the "Page X/Y" button in the ContainerPaginator. It allows the user to input a page number to jump to.
        :param trigger_view: The ContainerPaginator that triggered this modal. We need a reference to it to change the page and update the view after the user submits the modal.
        """
        super().__init__(title="Go to page")
        self.trigger_view: ContainerPaginator = trigger_view  # Store the original view
        self.total_pages = len(trigger_view.pages)

        self.page_input = discord.ui.InputText(
            label="Page Number", placeholder=f"Page (1-{self.total_pages})", required=True
        )
        self.add_item(self.page_input)

    async def callback(self, interaction: discord.Interaction):
        try:
            page_number = int(self.page_input.value)
            if 1 <= page_number <= self.total_pages:
                # trigger the site update
                self.trigger_view.set_page(page_number - 1)

                # update the paginator
                self.trigger_view.update_view()

                # edit the original view with the updated view
                await interaction.response.edit_message(view=self.trigger_view)
            else:
                await interaction.response.send_message(
                    f"Please input a number between 1 and {self.total_pages}.", ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message("Please input a valid number.", ephemeral=True)


class PageSelectButton(discord.ui.Button):
    def __init__(self, label: str):
        """
        A button that opens a PageSelectModal when clicked, allowing the user to input a page number to jump to.
        :param label: The buttons label, usually something like "Page X/Y". The actual page changing logic happens in the PageSelectModal's callback, this button just opens the modal.
        """
        super().__init__(label=label, style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        view: ContainerPaginator = self.view  # type: ignore
        await interaction.response.send_modal(PageSelectModal(trigger_view=view))


class ContainerPaginator(discord.ui.DesignerView):
    def __init__(self, author: discord.User | None = None, *, pages: list[discord.ui.Container] | None = None):
        """
        A view that can hold multiple Containers and display them one at a time with pagination buttons to switch between them.
        :param author: the user who can interact with this paginator. If None, anyone can interact with it.
        :param pages: the pages this paginator should start with. You can also add pages later with the add_page method. Each page is a Container.
        """
        super().__init__(timeout=120, disable_on_timeout=True)
        self.author = author
        self.current_page = 0
        if pages:
            for index, page in enumerate(pages):
                total_components = 0
                for item in page.walk_items():
                    if item.type is discord.ComponentType.action_row:
                        item: discord.ui.ActionRow
                        total_components += len(item.children)
                    elif item.type is discord.ComponentType.section:
                        item: discord.ui.Section
                        total_components += len(item.items)
                    elif item.type is discord.ComponentType.media_gallery:
                        item: discord.ui.MediaGallery
                        total_components += len(item.items)
                    else:
                        total_components += 1
                if total_components + 6 > 40:  # Reserve 6 components for actionrow + pagination buttons
                    raise ValueError(f"Page {index + 1} has too many components ({total_components}) limit is 40!")
        self.pages: list[discord.ui.Container] = pages or []

    def add_page(self, container: discord.ui.Container):
        """
        add a page to this paginator. Each page is a Container.
        :param container: ``discord.ui.Container`` to append to this paginator
        :return: None
        """
        total_components = 0
        for item in container.walk_items():
            if item.type is discord.ComponentType.action_row:
                item: discord.ui.ActionRow
                total_components += len(item.children)
            elif item.type is discord.ComponentType.section:
                item: discord.ui.Section
                total_components += len(item.items)
            elif item.type is discord.ComponentType.media_gallery:
                item: discord.ui.MediaGallery
                total_components += len(item.items)
            else:
                total_components += 1
        if total_components + 6 > 40:  # Reserve 6 components for actionrow + pagination buttons
            raise ValueError(f"{container} has too many components ({total_components}) limit is 40!")
        self.pages.append(container)

    def set_page(self, page: int):
        """
        set the current page of this paginator. This does not update the view, you need to call update_view after this to see the changes.
        :param page: the page in range len(pages) you want to switch to
        :return: None
        """
        self.current_page = page

    def _add_pagination_buttons(self):
        """
        add pagination buttons to the view. This should be called in the update_view method after adding the current page's container to the view, so that the buttons are always at the bottom.
        :return: None
        """
        if len(self.pages) > 1:
            first = PaginationButton("First", new_page=0, discord_id=100, disabled=(self.current_page == 0))
            prev = PaginationButton(
                "Previous", new_page=self.current_page - 1, discord_id=101, disabled=(self.current_page == 0)
            )
            page_select = PageSelectButton(f"Page {self.current_page + 1}/{len(self.pages)}")
            next_ = PaginationButton(
                "Next",
                new_page=self.current_page + 1,
                discord_id=102,
                disabled=(self.current_page == len(self.pages) - 1),
            )
            last = PaginationButton(
                "Last",
                new_page=len(self.pages) - 1,
                discord_id=103,
                disabled=(self.current_page == len(self.pages) - 1),
            )
            action_row = discord.ui.ActionRow(first, prev, page_select, next_, last)
            self.add_item(action_row)

    def update_view(self):
        """
        clear the view and add the current page's container and pagination buttons again. This should be called whenever you change the page or add/remove pages to update the view accordingly.
        :return: the updated view itself, so you can directly return it in an interaction response like: ``await interaction.response.edit_message(view=paginator.update_view())``
        """
        self.clear_items()
        self.add_item(self.pages[self.current_page])
        self._add_pagination_buttons()
        return self
