from logging import CRITICAL, DEBUG, ERROR, INFO, WARNING


class VersionInfo:
    def __init__(self, mayor: int, minor: int, patch: int, release_level: str):
        self.mayor = mayor
        self.minor = minor
        self.patch = patch
        self.release_level = release_level

    def __str__(self) -> str:
        return f"{self.mayor}.{self.minor}.{self.patch}{self.release_level}"


DISCORD_API_KEY = ""
GOOGLE_API_KEY = ""
DEBUG_GUILDS = [578446945425555464]
log_level = DEBUG

IPC_SECRET = "ihufsad"
client_version = VersionInfo(1, 2, 0, "a1")
