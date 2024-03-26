# Simple Docs
## Events
- on_tagesschau_entry
  - is dispatched every minute with a list of embeds containing news by the "Tagesschau"
  - **Parameters:**
    - List[discord.Embed]
- on_start_done
  - is dispatched after the initial on_ready event. since the `wait_until_ready` function dispatches too early for the
  database setup
- on_stat_counter
  - is linked up to a database to track stats
    - e.g. Minuets in voice, messages sent, requests made...
  - **Parameters:**
    - stat: `str`
      - e.g. Bad URLs
    - count: `int`
    - entry: `Optional[discord.User | discord.Member | discord.Guild | None | ...]`
