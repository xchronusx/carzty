# Command reference

Every reply is ephemeral (only you see it). Reminders themselves are the only thing Carzty posts publicly,
and only if you told it to post in a channel.

The `task` option on every command autocompletes from **your** tasks. Start typing part of the name or
the `#id`. Nobody else's tasks show up and nobody can touch yours.

---

## `/task add`

| Option | Required | What it is |
| --- | --- | --- |
| `what` | yes | The task. Up to 200 characters |
| `every` | no | How often it repeats. Leave it empty for a one-time reminder |
| `when` | for one-time | When the first reminder goes off |
| `nag` | no | Re-ping every X until you hit Done |
| `deliver` | no | `DM me` (default) or `Post in this channel` |
| `notes` | no | Extra details shown on the reminder. Up to 1000 characters |

How the first reminder gets picked:

- `every` + `when` → first one at `when`, then every `every` after that
- `every` only → first one is one interval from now (`every:2h` = 2 hours from now)
- `every:weekdays` (or any day list) with no `when` → next allowed day at 9am
- `when` only → one-time reminder at `when`
- neither → you get told off

If `when` lands on a day your schedule skips (say, a Saturday on a `weekdays` task), it rolls forward
to the next allowed day at the same time.

`deliver:Post in this channel` needs Carzty to actually be in the server with permission to post embeds
there. If it isn't (you're using it as a user-installed app, or perms are missing), it falls back to
DMs and tells you why.

## `/task list`

Everything that isn't finished, ringing stuff first. `show_done:True` includes finished one-time tasks.

Status icons:

| | |
| --- | --- |
| 🔔 | going off right now, waiting on you |
| ⏰ | scheduled |
| ⏸️ | paused |
| ✅ | done |
| 🔥 | current streak |
| ⚠️ | the last reminder had a delivery problem. `/task show` says what |

## `/task show`

Everything about one task. If it's going off, you get the Done/Snooze/Skip buttons here too.

## `/task done`

- **Going off right now** → acknowledged. Nagging stops, streak goes up, next one stays on schedule.
- **Recurring, not going off** → counts as doing the *next* one early. That next reminder gets skipped.
- **One-time** → finished. It sticks around in `/task list show_done:True` for 30 days, then gets deleted.

## `/task snooze`

Only works on a reminder that's going off. `for` takes a duration (`15m`, `2h`) or a time
(`5pm`, `tomorrow 9am`). When the snooze runs out you get the reminder again, and nagging picks back up.

Want to push back a reminder that *hasn't* gone off yet? That's `/task edit` with a new `when`, or `/task skip`.

## `/task skip`

- **Going off right now** → dismissed. No credit, but your streak isn't reset either. You skipped it on purpose.
- **Recurring, not going off** → the next occurrence gets skipped.
- **One-time, going off** → dismissed and closed.

## `/task pause` / `/task resume`

Paused tasks never fire. When you resume, it picks up at the next scheduled time after *now*. You don't
get a pile of everything that would've happened while it was paused.

## `/task edit`

Only fill in what you want to change.

- `every:once` turns a recurring task into a one-time one (needs a `when` unless one's already scheduled)
- `nag:off` turns nagging off
- `notes:clear` deletes the notes
- a new `when` on a finished one-time task brings it back

Changing `every` without a `when` keeps the time you already had. Daily-at-9 switched to `weekdays` is
still at 9.

## `/task remove`

Deleted immediately. No undo. Like real life.

---

## `/carzty timezone`

Autocompletes IANA names (type `phoenix`, `london`, `tokyo`...). This only changes how Carzty reads
times you *type*. Everything it shows you uses Discord timestamps, which already display in your local
time.

Existing tasks keep their current times. If you moved, `/task edit` them with a new `when`.

## `/carzty tone`

| Tone | Vibe |
| --- | --- |
| `chill` | Polite. Grandma-safe |
| `salty` | Sarcastic, mostly clean. The default |
| `unhinged` | Swears at you. Only you see your own tone, but if you post reminders in a channel, everyone does |

## `/carzty me` / `/carzty help` / `/carzty about`

Your settings and stats / the cheat sheet / version and uptime.

---

## The reminder itself

- ✅ **Done** - same as `/task done` on a ringing task
- 💤 **15m / 1h** - snooze (change these with `SNOOZE_OPTIONS` in `.env`)
- ⏭️ **Skip** - dismiss this one (recurring tasks only)

Only the task's owner can press them. Buttons keep working after the bot restarts, because the task ID is
baked into the button itself.

Nags escalate. The first couple are polite-ish. By nag #12 it's questioning your life choices. After
`MAX_NAGS` (24 by default) it gives up until the next scheduled reminder.

If the bot was offline when something was due, you get one reminder flagged as late, then it picks
back up on schedule.
