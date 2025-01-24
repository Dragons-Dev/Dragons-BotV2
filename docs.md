# Simple Docs
## Events

- on_webhook_entry
  - is dispatched every minute with a list of embeds
  - **Parameters:**
    - List[discord.Embed]
- on_start_done
  - is dispatched once after the initial on_ready event. since the `wait_until_ready` function dispatches too early for
    the database setup
