<p align="center">
  <a href="https://discord.gg/naweGHs9C7"><img src="https://img.shields.io/discord/578446945425555464?logo=discord&logoColor=%235865F2&label=Discord" alt="Discord server invite" /></a>
  <a href="https://github.com/Dragons-Dev/Dragons-BotV2/graphs/contributors"><img src="https://img.shields.io/github/contributors/Dragons-Dev/Dragons-BotV2" alt="Contributors" /></a>
  <a href="https://github.com/Dragons-Dev/Dragons-BotV2/releases"><img src="https://img.shields.io/github/v/release/Dragons-Dev/Dragons-BotV2" alt="Latest release" /></a>
  <a href="https://github.com/Dragons-Dev/Dragons-BotV2/commits"><img src="https://img.shields.io/github/commits-since/Dragons-Dev/Dragons-BotV2/latest" alt="Commit activity" /></a>
  <a href="https://github.com/Dragons-Dev/Dragons-BotV2/actions"><img src="https://github.com/Dragons-Dev/Dragons-BotV2/actions/workflows/github-code-scanning/codeql/badge.svg" alt="CodeQL status" /></a>
  <a href="https://www.codefactor.io/repository/github/dragons-dev/dragons-botv2"><img src="https://www.codefactor.io/repository/github/dragons-dev/dragons-botv2/badge" alt="CodeFactor" /></a>
</p>

# Dragons Bot V2

A modular Discord bot written in Python 3.13 with features for moderation, automation, utilities and server management.

## Highlights

- **Moderation toolkit**: ban, kick, timeout, warn, purge, voice moderation, bad URL checks and modmail.
- **Automation modules**: release announcements, Tagesschau news updates and join-to-create voice channels.
- **Utility commands**: password generation, NATO translator, user/bot stats and settings management.
- **Extension-based architecture**: commands are split by domain under `/extensions` and can be enabled/disabled.

## Project status

Planned features and ongoing work are tracked in the repository projects and issue tracker.

## Requirements

- Python **3.13**
- A Discord bot token from the [Discord Developer Portal](https://discord.com/developers/applications)
- Optional: Google Safe Browsing API key for URL scanning
- Optional: Spotify client credentials (for related integrations)

## Quick start (local)

1. Clone the repository.
2. Copy `.env.example` to `.env`.
3. Fill in required values (`DISCORD_API_KEY`, optionally the rest).
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Start the bot:
   ```bash
   python main.py
   ```

## Quick start (Docker)

1. Create a `.env` file (for example by copying `.env.example`).
2. Start the container:
   ```bash
   docker compose up -d
   ```

The compose setup stores persistent data in `./data`.

## Configuration

Environment variables are loaded from `.env` via `python-dotenv`.

| Variable | Required | Description |
| --- | --- | --- |
| `DISCORD_API_KEY` | Yes | Discord bot token |
| `DATABASE_URL` | No | SQLAlchemy database URL (default: sqlite in `/data`) |
| `GOOGLE_API_KEY` | No | Used for harmful URL checks |
| `log_level` | No | Bot log level (`DEBUG` or `INFO`) |
| `discord_log_level` | No | Discord logger verbosity |
| `IPC_SECRET` | No | Secret for bot ↔ web interface communication |
| `SPOTIFY_CLIENT_ID` | No | Spotify API client id |
| `SPOTIFY_CLIENT_SECRET` | No | Spotify API client secret |
| `SERVER_TZ` | No | Server timezone (e.g. `Europe/Berlin`) |

## Repository structure

- `/extensions` – bot feature modules (administration, moderation, automation, fun, stats, tools)
- `/utils` – shared utilities, database helpers, logging and core bot classes
- `/assets` – static bot assets and extension state
- `main.py` – startup logic and extension loading

## Contributing

Contributions are welcome. If you want to propose a feature or fix:

1. Open an issue (or pick an existing one)
2. Fork and create a branch
3. Open a pull request with a clear description

## Community

- Discord: https://discord.gg/naweGHs9C7
- Issues: https://github.com/Dragons-Dev/Dragons-BotV2/issues
