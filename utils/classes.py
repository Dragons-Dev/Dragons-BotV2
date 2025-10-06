from discord import ApplicationCommandError


class CommandDisabledError(ApplicationCommandError):
    pass


class InsufficientPermission(ApplicationCommandError):
    pass
