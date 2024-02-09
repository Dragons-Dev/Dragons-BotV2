# Simple Docs
## Events
- on_tagesschau_entry
  - is dispatched every minute with a list of embeds containing news by the "Tagesschau"
- on_start_done
  - is dispatched after the initial on_ready event. since the `wait_until_ready` function dispatches too early for the
  database setup
