from discord import User


def individual_users(users: list[User]):
    individual = set()
    for user in users:
        individual.add(user.id)
    return individual
