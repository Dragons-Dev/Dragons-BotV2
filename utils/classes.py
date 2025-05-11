from discord import Activity, ApplicationCommandError, Status


class BotActivity:
    def __init__(
            self,
            status: Status,
            activity: Activity,
    ):
        self.status = status
        self.activity = activity


class CommandDisabledError(ApplicationCommandError):
    pass


class InsufficientPermission(ApplicationCommandError):
    pass

    def __repr__(self):
        return f'BotActivity<{self.status}, {self.activity}>'
