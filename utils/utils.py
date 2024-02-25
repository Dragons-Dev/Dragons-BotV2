from discord import User


def individual_users(users: list[User]):
    individual = set()
    for user in users:
        individual.add(user.id)
    return individual


def sec_to_readable(time: float):
    hours, seconds = divmod(int(time), 60 * 60)
    minutes, seconds = divmod(seconds, 60)
    if not hours:
        return f"{minutes}m {seconds}s"
    return f"{hours}h {minutes}m {seconds}s"
