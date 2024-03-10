def sec_to_readable(time: float):
    hours, seconds = divmod(int(time), 60 * 60)
    minutes, seconds = divmod(seconds, 60)
    if not hours:
        return f"{minutes}m {seconds}s"
    return f"{hours}h {minutes}m {seconds}s"
