import logging
import os
from datetime import datetime as dt
from pathlib import Path

from colorama import Fore, Style

from config import log_level

FMT = "{levelname[0]} | [{asctime}] | [{name}] | [{module}:{lineno}] | {message}"

FORMATS = {
    logging.DEBUG: (
        Fore.WHITE
        + Style.BRIGHT
        + "{levelname[0]}"
        + Style.RESET_ALL
        + Fore.WHITE
        + " | "
        + "[{asctime},{msecs:n}]"
        + " | "
        + Style.BRIGHT
        + "[{name}]"
        + Style.RESET_ALL
        + Fore.WHITE
        + " | "
        + "[{module}:{lineno}]"
        + " | "
        + "{message}"
        + Style.RESET_ALL
    ),
    logging.INFO: (
        Fore.GREEN
        + Style.BRIGHT
        + "{levelname[0]}"
        + Style.RESET_ALL
        + Fore.GREEN
        + " | "
        + "[{asctime},{msecs:n}]"
        + " | "
        + Style.BRIGHT
        + "[{name}]"
        + Style.RESET_ALL
        + Fore.GREEN
        + " | "
        + "[{module}:{lineno}]"
        + " | "
        + "{message}"
        + Style.RESET_ALL
    ),
    logging.WARNING: (
        Fore.YELLOW
        + Style.BRIGHT
        + "{levelname[0]}"
        + Style.RESET_ALL
        + Fore.YELLOW
        + " | "
        + "[{asctime},{msecs:n}]"
        + " | "
        + Style.BRIGHT
        + "[{name}]"
        + Style.RESET_ALL
        + Fore.YELLOW
        + " | "
        + "[{module}:{lineno}]"
        + " | "
        + "{message}"
        + Style.RESET_ALL
    ),
    logging.ERROR: (
        Fore.RED
        + Style.BRIGHT
        + "{levelname[0]}"
        + Style.RESET_ALL
        + Fore.RED
        + " | "
        + "[{asctime},{msecs:n}]"
        + " | "
        + Style.BRIGHT
        + "[{name}]"
        + Style.RESET_ALL
        + Fore.RED
        + " | "
        + "[{module}:{lineno}]"
        + " | "
        + "{message}"
        + Style.RESET_ALL
    ),
    logging.CRITICAL: (
        Fore.RED
        + Style.BRIGHT
        + "{levelname[0]}"
        + " | "
        + "[{asctime},{msecs:n}]"
        + " | "
        + Style.BRIGHT
        + "[{name}]"
        + " | "
        + "[{module}:{lineno}]"
        + " | "
        + "{message}"
        + Style.RESET_ALL
    ),
}


class CustomFormatter(logging.Formatter):
    """A custom formatter for the console logger"""

    def format(self, record):
        log_fmt = FORMATS[record.levelno]
        formatter = logging.Formatter(log_fmt, style="{", datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def rem_log():
    if not Path("logs").exists():
        os.mkdir("logs")
    while len(os.listdir("logs")) > 7:
        for file in os.listdir("logs"):
            os.remove("logs/" + file)
            break


class CustomLogger(logging.Logger):
    """A custom file and console logger"""

    def __init__(self, name, start_stamp: dt):
        rem_log()
        self.name = name
        super().__init__(name=self.name)
        self.start_stamp = start_stamp
        file_handler = logging.FileHandler(f"logs/{self.start_stamp.strftime('%Y-%m-%d_%H+%M')}.log", "a")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(FMT, style="{", datefmt="%Y-%m-%d %H:%M:%S"))
        self.addHandler(file_handler)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(CustomFormatter())
        self.addHandler(console_handler)


if __name__ == "__main__":
    log = CustomLogger(start_stamp=dt.now(), name="hey")
    log.debug("Debug")
    log.info("Info")
    log.warning("Warning")
    log.error("Error")
    log.critical("Critical")
    rem_log()
