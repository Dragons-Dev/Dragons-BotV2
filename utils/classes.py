from discord import Activity, Status


class BotActivity:
    def __init__(
            self,
            status: Status,
            activity: Activity,
    ):
        self.status = status
        self.activity = activity
