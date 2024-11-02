class VersionInfo:
    def __init__(self, mayor: int, minor: int, patch: int, release_level: str):
        self.mayor = mayor
        self.minor = minor
        self.patch = patch
        self.release_level = release_level

    def __str__(self) -> str:
        return f"{self.mayor}.{self.minor}.{self.patch}{self.release_level}"

    def __hash__(self):
        return hash((self.mayor, self.minor, self.patch, self.release_level))


def sec_to_readable(time: float) -> str:
    """
    Takes a time in seconds as float.
    Args:
        time: the time in seconds

    Returns:
        str: formatted time in readable format (h) m s
    """
    hours, seconds = divmod(int(time), 60 * 60)
    minutes, seconds = divmod(seconds, 60)
    if not hours:
        return f"{minutes}m {seconds}s"
    return f"{hours}h {minutes}m {seconds}s"
