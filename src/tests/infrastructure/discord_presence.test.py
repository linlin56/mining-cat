import time

from miningcat.infrastructure.system.discord_presence import Activity, DiscordPresence
from pypresence.exceptions import DiscordNotFound, PipeClosed


class FakeClient:
    def __init__(self):
        self.updates, self.cleared, self.closed = [], 0, False

    def update(self, **fields):
        self.updates.append(fields)

    def clear(self):
        self.cleared += 1

    def close(self):
        self.closed = True


READING = Activity(details="Reading a book", state="Studying Japanese", large_image="logo", large_text="MiningCat")


def test_sends_the_activity_once():
    client = FakeClient()
    presence = DiscordPresence("123", connect=lambda: client)
    presence.show(READING)
    presence.sync()
    presence.sync()
    assert len(client.updates) == 1
    assert client.updates[0]["details"] == "Reading a book"
    assert client.updates[0]["state"] == "Studying Japanese"
    assert client.updates[0]["large_image"] == "logo"
    presence.show(None)
    presence.sync()
    assert client.cleared == 1


def test_waits_for_discord_to_be_opened():
    client = FakeClient()
    attempts = []

    def connect():
        attempts.append(1)
        if len(attempts) == 1:
            raise DiscordNotFound
        return client

    presence = DiscordPresence("123", connect=connect)
    presence.show(READING)
    presence.sync()
    assert client.updates == []
    presence.sync()
    assert len(client.updates) == 1


def test_connects_again_when_discord_is_closed():
    first, second = FakeClient(), FakeClient()
    clients = iter([first, second])
    presence = DiscordPresence("123", connect=lambda: next(clients))
    presence.show(READING)
    presence.sync()

    def closed(**fields):
        raise PipeClosed
    first.update = closed
    presence.show(Activity(details="Watching a video"))
    presence.sync()
    assert first.closed
    presence.sync()
    assert second.updates[0]["details"] == "Watching a video"
    assert second.updates[0]["state"] is None


def test_without_an_application_id_it_never_starts():
    presence = DiscordPresence("", connect=FakeClient)
    assert not presence.available
    presence.start()
    presence.show(READING)
    presence.stop()


def test_the_thread_sends_and_stops():
    client = FakeClient()
    presence = DiscordPresence("123", connect=lambda: client, interval=0.01)
    presence.show(READING)
    presence.start()
    for _ in range(200):
        if client.updates:
            break
        time.sleep(0.01)
    presence.stop()
    assert client.updates and client.closed
