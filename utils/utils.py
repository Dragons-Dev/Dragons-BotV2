class VersionInfo:
    def __init__(self, mayor: int, minor: int, patch: int, release_level: str):
        self.mayor = mayor
        self.minor = minor
        self.patch = patch
        self.release_level = release_level

    def __str__(self) -> str:
        return f"{self.mayor}.{self.minor}.{self.patch}{self.release_level}"


def sec_to_readable(time: float):
    hours, seconds = divmod(int(time), 60 * 60)
    minutes, seconds = divmod(seconds, 60)
    if not hours:
        return f"{minutes}m {seconds}s"
    return f"{hours}h {minutes}m {seconds}s"
