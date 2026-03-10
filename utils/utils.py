class VersionInfo:
    def __init__(self, mayor: int, minor: int, patch: int, release_level: str):
        self.mayor = mayor
        self.minor = minor
        self.patch = patch
        self.release_level = release_level

    def __str__(self) -> str:
        return f"{self.mayor}.{self.minor}.{self.patch}{self.release_level}"

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other: "VersionInfo") -> bool:
        return (
            self.mayor == other.mayor
            and self.minor == other.minor
            and self.patch == other.patch
            and self.release_level == other.release_level
        )

    def __ne__(self, other: "VersionInfo") -> bool:
        return not self == other

    def __lt__(self, other: "VersionInfo") -> bool:
        if self.mayor < other.mayor:
            return True
        elif self.mayor == other.mayor:
            if self.minor < other.minor:
                return True
            elif self.minor == other.minor:
                if self.patch < other.patch:
                    return True
                elif self.patch == other.patch:
                    # How compare release level??????????
                    return False
                else:
                    return False
            else:
                return False
        else:
            return False

    def __le__(self, other: "VersionInfo") -> bool:
        if self.mayor < other.mayor:
            return True
        elif self.mayor == other.mayor:
            if self.minor < other.minor:
                return True
            elif self.minor == other.minor:
                if self.patch < other.patch:
                    return True
                elif self.patch == other.patch:
                    return True
                else:
                    return False
            else:
                return False
        else:
            return False

    def __gt__(self, other: "VersionInfo") -> bool:
        if self.mayor > other.mayor:
            return True
        elif self.mayor == other.mayor:
            if self.minor > other.minor:
                return True
            elif self.minor == other.minor:
                if self.patch > other.patch:
                    return True
                elif self.patch == other.patch:
                    # How compare release level??????????
                    return False
                else:
                    return False
            else:
                return False
        else:
            return False

    def __ge__(self, other: "VersionInfo") -> bool:
        if self.mayor > other.mayor:
            return True
        elif self.mayor == other.mayor:
            if self.minor > other.minor:
                return True
            elif self.minor == other.minor:
                if self.patch > other.patch:
                    return True
                elif self.patch == other.patch:
                    return True
                else:
                    return False
            else:
                return False
        else:
            return False

    @classmethod
    def from_str(cls, other: str) -> "VersionInfo":
        try:
            mayor, minor, patch_release = other.lower().strip().split(".")
            patch = ""
            for char in patch_release:
                if char.isnumeric():
                    patch += char
                else:
                    break
            if mayor.startswith("v"):
                mayor = mayor[1:]
            if patch == "":
                patch = "0"
            return VersionInfo(int(mayor), int(minor), int(patch), patch_release.replace(patch, "", 1).strip())
        except Exception as e:
            print(e)


def sec_to_readable(time: int | float) -> str:
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
