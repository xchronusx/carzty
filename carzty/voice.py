##xchronusx
"""
carzty.voice - the attitude.

Synopsis:
    say("salty", "scheduled")
    say("unhinged", "nag", nag=7)

Description:
    Three tones. Pick a default in .env (DEFAULT_TONE), and anybody can override
    it for themselves with /carzty tone.

      chill    - polite. your grandma could use this one.
      salty    - the default. sarcastic, mostly clean.
      unhinged - swears. opt in only. don't turn this on in your work server and then email me.

    Nag lines escalate the longer you ignore it. That's the whole point.

Notes:
    Author: Zachary Wright (xchronusx)
    Want more lines? Add 'em to the lists. Placeholders available: {title} {nag} {streak} {until} {due}
    PRs with better insults are welcome.
"""

from __future__ import annotations

import random

LINES: dict[str, dict[str, list[str]]] = {
    #region CHILL
    "chill": {
        "added": ["All set. I'll remind you.", "Got it, it's on the list.", "Saved. I've got you."],
        "scheduled": ["Friendly reminder.", "Hey, it's time for this one.", "Quick heads up."],
        "late": ["Sorry, I was offline for a bit. This was due {due}."],
        "missed": ["Looks like the last one didn't get marked done, no worries."],
        "nag_1": ["Just checking back on this one.", "Gentle nudge."],
        "nag_2": ["Still on your list.", "Another nudge, whenever you're ready."],
        "nag_3": ["This one's still waiting on you.", "Popping back in on this."],
        "nag_4": ["Still here, still reminding.", "Hey, one more nudge."],
        "snooze_over": ["Snooze is over.", "Back again, as requested."],
        "gave_up": ["That's my last reminder for this round."],
        "done": ["Nice work!", "Done and done.", "Checked off."],
        "done_streak": ["Nice work, that's {streak} in a row."],
        "done_early": ["Ahead of schedule, love it. I'll skip the next one."],
        "snoozed": ["Snoozed until {until}."],
        "skipped": ["Skipped. See you next time."],
        "dismissed": ["Dismissed."],
        "paused": ["Paused. I'll stay quiet until you resume it."],
        "resumed": ["Back on."],
        "removed": ["Removed."],
        "not_yours": ["That one belongs to someone else."],
    },
    #endregion

    #region SALTY
    "salty": {
        "added": [
            "Locked in. I'll be the one bugging you about it.",
            "Saved. Don't make me regret this.",
            "Done. Future you is gonna love me. Or hate me. One of those.",
            "Noted. Unlike you, I don't forget things.",
        ],
        "scheduled": [
            "Hey. It's time.",
            "Reminder, since you'd absolutely forget otherwise.",
            "Yo. This thing. Now-ish.",
            "You asked me to do this, so don't get mad.",
            "Ding ding. Your move.",
        ],
        "late": [
            "Okay so I was napping. This was due {due}. My bad. Still your problem though.",
            "I was offline and missed it. This was due {due}. Go.",
        ],
        "missed": [
            "Also, you never finished the last one. Just saying.",
            "Last time didn't get a Done either. I see you.",
        ],
        "nag_1": ["Still waiting.", "Hello? Still a thing.", "Did you do it? You did not."],
        "nag_2": [
            "Nag #{nag}. I have nothing but time.",
            "Still not done. I'm not going anywhere.",
            "This is me, still here, being a pest.",
        ],
        "nag_3": [
            "Nag #{nag}. I'm not mad. I'm just disappointed.",
            "At this point the task is doing a better job existing than you are doing it.",
            "You know there's a Done button, right? Big green one.",
        ],
        "nag_4": [
            "Nag #{nag}. I'm basically part of your personality now.",
            "This is a cry for help. Mine. Please hit Done.",
            "I've nagged {nag} times. My therapist says I should stop. I won't.",
        ],
        "snooze_over": ["Snooze is over. Up and at 'em.", "Wakey wakey. Snooze expired.", "Back, as threatened."],
        "gave_up": ["That's my last nag. I'm not your mom. (I'll be back next time though.)"],
        "done": ["Look at you go.", "Proud of you. Kinda.", "Finally.", "Wow. Productivity. Gross."],
        "done_streak": ["{streak} in a row. Who even are you?", "Streak: {streak}. Don't blow it."],
        "done_early": ["Early? Who are you and what did you do with the real you. Skipping the next one."],
        "snoozed": ["Fine. Until {until}. Not a second more.", "Snoozed until {until}. I'll be back."],
        "skipped": ["Skipped. I'll allow it. This time."],
        "dismissed": ["Dismissed. No credit though."],
        "paused": ["Paused. I'll pretend I don't know about it."],
        "resumed": ["Aaaand we're back."],
        "removed": ["Gone. Like it never happened. Very healthy."],
        "not_yours": ["Not your task, chief.", "Hands off, that's somebody else's problem."],
    },
    #endregion

    #region UNHINGED
    "unhinged": {
        "added": [
            "Locked in. I will haunt you.",
            "Saved. You're gonna do this shit whether you like it or not.",
        ],
        "scheduled": [
            "Do the damn thing.",
            "Hey dipshit, it's time.",
            "It's go time. Move your ass.",
            "Reminder. Don't make it weird.",
        ],
        "late": ["I was dead for a bit. This was due {due}. Still do it."],
        "missed": ["You blew off the last one too. Incredible."],
        "nag_1": ["Still waiting, jackass.", "Hello?? Do it."],
        "nag_2": ["Nag #{nag}. I can do this all day.", "Still not done? Cool. Cool cool cool."],
        "nag_3": ["Nag #{nag}. For fuck's sake.", "I'm starting to take this personally."],
        "nag_4": ["Nag #{nag}. I hope you're happy.", "This is nag {nag}. I've lost the will to live. Hit Done."],
        "snooze_over": ["Snooze is over. Get up.", "Nap time's done, princess."],
        "gave_up": ["I give up. You win. (You don't actually win.)"],
        "done": ["Hell yeah.", "Holy shit, you did it.", "Took you long enough."],
        "done_streak": ["{streak} in a row. Look at you, not being a disaster."],
        "done_early": ["Early?? Who the hell are you. Skipping the next one."],
        "snoozed": ["Fine. {until}. Don't push it."],
        "skipped": ["Skipped. Coward. (Respectfully.)"],
        "dismissed": ["Dismissed. Weak, but okay."],
        "paused": ["Paused. I'll shut up. For now."],
        "resumed": ["I'm back, bitches."],
        "removed": ["Yeeted."],
        "not_yours": ["Not your task. Back off."],
    },
    #endregion
}


def nag_key(nag: int) -> str:
    if nag <= 2:
        return "nag_1"
    if nag <= 5:
        return "nag_2"
    if nag <= 11:
        return "nag_3"
    return "nag_4"


def say(tone: str | None, key: str, rng: random.Random | None = None, **fmt) -> str:
    """Grab a random line for `key` in `tone`. Falls back to salty, then to nothing."""
    rng = rng or random
    if key == "nag":
        key = nag_key(int(fmt.get("nag", 1)))
    table = LINES.get(tone or "salty") or LINES["salty"]
    options = table.get(key) or LINES["salty"].get(key) or [""]
    line = rng.choice(options)
    try:
        return line.format(**fmt)
    except (KeyError, IndexError):
        return line  # somebody added a line with a placeholder we didn't pass. not worth crashing over
##xchronusx
