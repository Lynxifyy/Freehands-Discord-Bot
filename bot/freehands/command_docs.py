"""Plain-English command descriptions for the console app.

Kept apart from cmd_impl.py so the wording can be edited without touching
handler code, and so the console can show a real explanation instead of the
one-line list summary.
"""

from __future__ import annotations

DETAILS: dict[str, str] = {
    # -- owner ------------------------------------------------------------
    "antiban": "Turns ban protection on or off. While it is on, the bot refuses "
               "to ban anyone and instead asks you to approve the ban first. This "
               "stops a compromised account or a mistyped command from wiping the "
               "member list.",
    "approve": "Approves the ban that is waiting for a decision. Use it after "
               "+ban was held back by ban protection and you are sure you want "
               "the person gone.",
    "automod": "Turns automatic moderation on or off. When it is on, the bot "
               "deletes spam, invites, slurs and mass mentions on its own without "
               "waiting for you.",
    "glaze": "Turns the flattering replies on or off. When it is on, any message "
             "that mentions Lynx gets one admiring line back, at most once every "
             "45 seconds per channel, and never the same line twice in a row.",
    "loopban": "Bans the same member again and again on a timer. You choose how "
               "many passes and how far apart. It always ends by itself: there is "
               "no option to run forever. The owner and Lynx cannot be targeted.",
    "loopkick": "Kicks the same member again and again on a timer, for someone who "
                "keeps rejoining but should not be permanently banned. Same limits "
                "as +loopban: a pass count, an interval, and no protected targets.",
    "loops": "Lists every loop that is armed, how many passes it has done, and "
             "whether it is still running. Use it to check what is still firing "
             "before you leave.",
    "loopstop": "Stops one loop by its id, or every loop at once with +loopstop "
                "all. Loops also stop on their own when they run out of passes.",
    "ban": "Bans a member with an optional reason. While ban protection is on this "
            "does not ban straight away. It queues the ban and asks for +approve.",
    "clearstrikes": "Resets a member's strike count to zero. Strikes add up from "
                    "repeated offences, and enough of them locks the channel.",
    "codesense": "Turns code sensing on or off. When it is on, typing a code such "
                 "as code 8 pings Arceus and the owner with the eyes emoji and "
                 "moves the alert into a private room.",
    "demote": "Strips every role from a member, including Eternal, then tells them "
              "why in a direct message and pings you in the channel and by direct "
              "message. The roles are saved first, so +restore can undo it.",
    "deny": "Denies the ban that is waiting for a decision and clears it from the "
            "queue. The member stays.",
    "keepbanned": "Adds or removes a member from the anti-ban exception list. "
                  "People on this list stay banned even when ban protection is "
                  "switched on.",
    "kick": "Kicks a member from the server. They can rejoin with a new invite, so "
            "this is for a warning that stings, not for removing someone for good.",
    "lock": "Locks the current channel so ordinary members cannot type in it. "
            "Operators keep talking.",
    "lockvote": "Casts your vote on whether to start a server-wide lockdown. The "
                "lockdown starts once enough operators agree.",
    "mod": "Turns moderation on or off. This is the master switch. With it off, "
           "automod, strikes and mutes all stop acting.",
    "nomute": "Freezes or unfreezes all mutes. While frozen, the bot will not time "
              "anyone out, which is useful during an argument you want to handle "
              "yourself.",
    "ops": "Creates, locks or reports the private operator channel. Only you, "
           "Arceus, Lynx and the bot can read it. Anyone else who joins is removed.",
    "recover": "Gives the named member co-owner rights. Use it when you need a "
               "second pair of hands and you trust them completely.",
    "restore": "Puts back the roles that were saved for a member. This undoes "
               "+bankrupt, +takeall or +demote.",
    "say": "Makes the bot post your text in the channel. Useful for announcements "
           "that should come from the bot rather than from you.",
    "snapshot": "Saves a copy of a member's current roles. Run it before stripping "
                "someone so +restore has something to put back.",
    "takeall": "Strips every role from a member without telling them. This is the "
               "quiet version of +demote.",
    "temp ownership": "Lends ownership of the server to a member for a set number "
                      "of minutes, ten by default. When the time runs out the bot "
                      "takes it back automatically. Only you can run this.",
    "unban": "Lifts a ban so the person can rejoin with an invite.",
    "unlock": "Unlocks the current channel so ordinary members can type again.",
    "watch": "Turns the watch feature on or off. This is the master switch. With "
             "it on, the bot logs every message from the watched member and checks "
             "them for slurs, invites and mass mentions.",
    "watchtarget": "Arms or disarms the watch on the flagged member. While armed, "
                   "every message they send is copied to the operator channel with "
                   "the time and a flag list.",
    # -- mod --------------------------------------------------------------
    "incidents": "Lists the most recent code hits, newest first, with who raised "
                 "them and when. Pass a number to see more.",
    "mute": "Times a member out so they cannot speak for a while, ten minutes by "
            "default. Add a reason to explain it to them.",
    "purge": "Deletes the most recent messages in the channel, ten by default. "
             "Only messages the bot can remove are affected.",
    "strikes": "Shows how many strikes a member has and what each one was for.",
    "unmute": "Clears a timeout early so the member can speak again.",
    "test": "Checks that the bot really works: the Discord token, the gateway, "
            "the guild, the console log, pairing and the command list. Each "
            "line says OK or FAIL, so you can see what is broken at a glance.",
    "pair": "Connects the phone app without typing a URL or a token. Run +pair "
            "with no code and the bot gives you a six-character code; the app "
            "shows the same code, and you run +pair <code> with it. The phone "
            "then gets a token of its own, shown once.",
    "devices": "Lists every phone that can control the bot, when it was paired "
               "and when it last checked in. Use it to spot a device you do not "
               "recognise.",
    "revoke": "Disconnects a paired phone. Use +revoke <id> for one device or "
              "+revoke all for every device. Do this if a phone is lost or you "
              "think a token leaked.",
    "whois": "Shows a short summary of a member: their name, when they joined, "
             "their roles and their strike count.",
    # -- everyone ---------------------------------------------------------
    "bankrupt": "Strips every role from a member and sends them a direct message "
                "explaining it. Unlike +demote this is reversible and does not "
                "ping you.",
    "codes": "Lists the codebook so you can see what each code means and who it "
             "alerts.",
    "help": "Lists the commands you are allowed to use.",
    "ping": "Checks that the bot is awake and shows how long it took to answer.",
    "question": "Sends a question to the operators so it does not get lost in the "
                "main chat.",
    "stats": "Shows counters and how long the bot has been running.",
}


def detail_for(name: str, summary: str = "") -> str:
    """Full description, falling back to the summary when none is written."""
    text = DETAILS.get(name.lower().strip())
    if text:
        return text
    return summary or "No description written yet."
