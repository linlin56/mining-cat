"""The Discord status of the user (Settings › User preferences): the page they're on and the language they study.

It needs a Discord application (https://discord.com/developers/applications): its name is the one Discord shows
("Playing MiningCat"), its Application ID goes in DISCORD_CLIENT_ID or the MININGCAT_DISCORD_CLIENT_ID environment
variable, and an image named "logo" in its Rich Presence › Art Assets is shown next to the status.
"""
import os

from flask import request

from miningcat.application import study_language, user_preferences
from miningcat.domain.languages import LANGUAGES
from miningcat.infrastructure.system.discord_presence import Activity, DiscordPresence

DISCORD_CLIENT_ID = "1558140415755165768"
LOGO = "logo"

# The pages (Flask endpoints) and what the user does there; (without, with) an id in the URL for the libraries.
PAGES = {
    "pages.home": "In the menu",
    "pages.converter": "Making mineable videos",
    "pages.game": "Playing a game",
    "pages.clipboard": "Reading a text",
    "pages.settings": "In the settings",
    "comics.comic_page": "Reading a comic",
    "books.page": ("Choosing a book", "Reading a book"),
    "player.page": ("Choosing a video", "Watching a video"),
}


def client_id() -> str:
    return os.environ.get("MININGCAT_DISCORD_CLIENT_ID", DISCORD_CLIENT_ID).strip()


def why_off() -> str:
    try:
        import pypresence  # noqa: F401
    except ImportError:
        return "pypresence isn't installed (make install)."
    return "no Discord Application ID (DISCORD_CLIENT_ID or MININGCAT_DISCORD_CLIENT_ID)."


def page_activity(endpoint: str | None, view_args: dict | None) -> str | None:
    doing = PAGES.get(endpoint or "")
    if isinstance(doing, tuple):
        doing = doing[1] if any(view_args or {}) else doing[0]
    return doing


class DiscordStatus:
    def __init__(self, presence: DiscordPresence):
        self.presence = presence
        self.doing: str | None = None

    def page_opened(self) -> None:
        """before_request hook: a page of MiningCat was opened in the browser."""
        doing = page_activity(request.endpoint, request.view_args) if request.method == "GET" else None
        if doing:
            self.doing = doing
            self.refresh()

    def refresh(self) -> None:
        """Shows the last page opened, or nothing if the user turned it off."""
        if not self.doing or user_preferences.get_preferences()["discord"] != "on":
            self.presence.show(None)
            return
        language = study_language.current()
        self.presence.show(Activity(details=self.doing, state=f"Studying {LANGUAGES[language]}" if language else "",
                                    large_image=LOGO, large_text="MiningCat"))
