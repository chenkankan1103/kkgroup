"""
Local simulator for NewYearRedEnvelope interaction handling.

Scenarios covered:
- immediate claim (正常情況)
- delayed claim (等待一段時間後再按鈕)
- defer failure (模擬 interaction.response.defer() 拋例外)
- slow defer (紀錄 defer_elapsed > 3s)

Run: python tools/simulate_red_envelope.py
"""
import asyncio
import json
import logging
import os
import time
from types import SimpleNamespace

from uicommands.new_year_red_envelope import RedEnvelopeView, _load_storage, _save_storage, STORAGE_FILE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simulate_red_envelope")

# --- Mocks -----------------------------------------------------------------
class MockResponse:
    def __init__(self):
        self._done = False
        self.sent = []
        # control behavior: None|'raise'|'sleep'
        self.defer_behavior = None
        self.defer_sleep = 0

    async def defer(self, ephemeral=False):
        if self.defer_behavior == 'raise':
            raise Exception('simulated defer failure')
        if self.defer_behavior == 'sleep':
            await asyncio.sleep(self.defer_sleep)
        self._done = True

    def is_done(self):
        return self._done

    async def send_message(self, content, ephemeral=False):
        self._done = True
        self.sent.append(content)
        return content

class MockFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, content, ephemeral=False):
        self.messages.append(content)
        return content

class MockMessage:
    def __init__(self, id_):
        self.id = id_
        self.embeds = []
        self.components = []
        self.edited = []

    async def edit(self, embed=None, view=None):
        self.edited.append((embed, view))
        return None

class MockChannel:
    def __init__(self):
        self.sent_messages = {}

    async def send(self, embed=None, view=None):
        m = MockMessage(int(time.time() * 1000) % 1000000)
        self.sent_messages[m.id] = m
        return m

    async def fetch_message(self, mid):
        # return a stored message when possible (simplified)
        for m in self.sent_messages.values():
            if m.id == mid:
                return m
        # fallback: return a dummy
        return MockMessage(mid)

# Minimal cog-like object that the View expects
class MockCog:
    def __init__(self):
        self._pending = []
        self.bot = SimpleNamespace()
        self.bot.get_channel = lambda cid: self._channel if hasattr(self, '_channel') else None

    async def _award_user_with_retries(self, user_id, amount=0):
        # simulate successful award (return new balance)
        return 9999

    async def _add_pending_award(self, user_id, message_id, amount=0):
        self._pending.append((user_id, message_id, amount))

    async def _fetch_channel_for_message(self, message_id):
        return getattr(self, '_channel', None)

# Mock Interaction
class MockInteraction:
    def __init__(self, user_id, message: MockMessage, channel: MockChannel):
        self.user = SimpleNamespace(id=user_id, guild_permissions=SimpleNamespace(manage_guild=True, administrator=True))
        self.message = message
        self.channel = channel
        self.response = MockResponse()
        self.followup = MockFollowup()

# ---------------------------------------------------------------------------

def _safe_repr(s: str) -> str:
    if not isinstance(s, str):
        return repr(s)
    try:
        return s.encode('unicode_escape').decode('ascii')
    except Exception:
        return repr(s)

async def run_simulation():
    # clean storage
    try:
        if STORAGE_FILE.exists():
            STORAGE_FILE.unlink()
    except Exception:
        pass

    cog = MockCog()
    channel = MockChannel()
    cog._channel = channel

    activity_id = 'sim123'
    expiry = time.time() + 3600
    view = RedEnvelopeView(cog, activity_id=activity_id, message_id=1111, expiry_ts=expiry, claimed=[])

    # prepare a mock message and interaction
    message = MockMessage(1111)
    interaction1 = MockInteraction(user_id=1001, message=message, channel=channel)

    # Scenario 1 — immediate claim
    print('\n--- Scenario 1: immediate claim')
    start = time.time()
    await view._on_claim(interaction1)
    dur = time.time() - start
    print('followup messages:', [_safe_repr(m) for m in interaction1.followup.messages])
    storage = _load_storage()
    print('storage messages keys:', list(storage.get('messages', {}).keys()))
    print('elapsed handler (s):', f'{dur:.3f}')

    # Scenario 2 — delayed claim (simulate "幾分鐘後")
    print('\n--- Scenario 2: delayed claim (simulate wait, then press)')
    await asyncio.sleep(1)  # simulate time passing (use 1s instead of minutes for speed)
    interaction2 = MockInteraction(user_id=1002, message=message, channel=channel)
    start = time.time()
    await view._on_claim(interaction2)
    dur2 = time.time() - start
    print('followup messages:', [_safe_repr(m) for m in interaction2.followup.messages])
    print('storage claimed lists:', _load_storage().get('messages', {}).get(str(view.message_id), {}).get('claimed'))
    print('elapsed handler (s):', f'{dur2:.3f}')

    # Scenario 3 — defer raises exception
    print('\n--- Scenario 3: defer raises exception (simulate defer failure)')
    interaction3 = MockInteraction(user_id=1003, message=message, channel=channel)
    interaction3.response.defer_behavior = 'raise'
    start = time.time()
    await view._on_claim(interaction3)
    dur3 = time.time() - start
    print('response.sent (after defer failure):', [_safe_repr(m) for m in getattr(interaction3.response, 'sent', [])])
    print('followup messages:', [_safe_repr(m) for m in interaction3.followup.messages])
    print('elapsed handler (s):', f'{dur3:.3f}')

    # Scenario 4 — slow defer (sleep > 3s) to record defer_elapsed
    print('\n--- Scenario 4: slow defer (simulate defer taking >3s)')
    interaction4 = MockInteraction(user_id=1004, message=message, channel=channel)
    interaction4.response.defer_behavior = 'sleep'
    interaction4.response.defer_sleep = 3.5
    start = time.time()
    await view._on_claim(interaction4)
    dur4 = time.time() - start
    print('followup messages:', [_safe_repr(m) for m in interaction4.followup.messages])
    print('elapsed handler (s):', f'{dur4:.3f}')

    print('\nSimulation complete. Inspect logs for `red_envelope: defer done` and `red_envelope: claim finished` entries.')

if __name__ == '__main__':
    asyncio.run(run_simulation())
