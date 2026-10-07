"""Terminal client for the spoken interview (decisions 039, 045).

Stands in for the frontend until it exists:

    uv run python scripts/interview_cli.py <session_token> [ws://localhost:8002/v1/ws/interview]

Get a token from Core API's POST /v1/interviews. Each question is printed
and played through your speakers. When it finishes:

    Enter          start recording; Enter again to stop and send
    /t <answer>    type the answer instead
    /end           finish the interview early
"""

from __future__ import annotations

import asyncio
import json
import sys

import sounddevice as sd
import websockets

# Protocol audio formats (decision 045): PCM16 mono.
MIC_RATE = 16_000
SPEAKER_RATE = 24_000
MIC_BLOCK = MIC_RATE // 10  # 100 ms of samples per frame sent

# Server errors that leave the turn open for another attempt.
_RETRY_CODES = {"no_speech", "answer_too_long"}


class Speaker:
    """Plays question audio as it streams in, without blocking the socket.

    `RawOutputStream.write` blocks until the device has room, so writes run
    in a worker thread fed by a queue.
    """

    def __init__(self) -> None:
        self._stream = sd.RawOutputStream(samplerate=SPEAKER_RATE, channels=1, dtype="int16")
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._leftover = b""
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._stream.start()
        self._task = asyncio.create_task(self._run())

    def feed(self, chunk: bytes) -> None:
        # Network chunks needn't align to 2-byte samples; hold back an odd byte.
        data = self._leftover + chunk
        cut = len(data) - len(data) % 2
        self._leftover = data[cut:]
        if cut:
            self._queue.put_nowait(data[:cut])

    async def drain(self) -> None:
        """Wait until everything fed so far has been written to the device."""
        await self._queue.join()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            chunk = await self._queue.get()
            try:
                await loop.run_in_executor(None, self._stream.write, chunk)
            finally:
                self._queue.task_done()

    def close(self) -> None:
        if self._task:
            self._task.cancel()
        self._stream.stop()
        self._stream.close()


async def record_until_enter(ws) -> None:
    """Stream mic audio to the server until Enter, then send audio.end."""
    loop = asyncio.get_running_loop()
    frames: asyncio.Queue[bytes | None] = asyncio.Queue()

    def on_audio(indata, _frames, _time, status) -> None:
        # Runs on the audio thread: hand off to the event loop, nothing more.
        loop.call_soon_threadsafe(frames.put_nowait, bytes(indata))

    async def send_frames() -> None:
        while (frame := await frames.get()) is not None:
            await ws.send(frame)  # bytes → a binary frame

    mic = sd.RawInputStream(
        samplerate=MIC_RATE, channels=1, dtype="int16", blocksize=MIC_BLOCK, callback=on_audio
    )
    sender = asyncio.create_task(send_frames())
    with mic:
        print("  * recording... press Enter to stop", flush=True)
        await loop.run_in_executor(None, input)
    # The mic is closed, so no new callbacks. Yield once so hand-offs already
    # scheduled run first; then the sentinel goes in last and the sender
    # finishes every frame queued before it.
    await asyncio.sleep(0)
    frames.put_nowait(None)
    await sender
    await ws.send(json.dumps({"type": "audio.end"}))
    print("  (transcribing...)")


async def answer(ws) -> None:
    loop = asyncio.get_running_loop()
    try:
        line = await loop.run_in_executor(None, input, "[Enter] speak | /t <text> | /end > ")
    except EOFError:  # stdin closed: end politely
        line = "/end"
    line = line.strip()
    if line == "/end":
        await ws.send(json.dumps({"type": "session.end"}))
    elif line.startswith("/t "):
        await ws.send(json.dumps({"type": "answer.text", "text": line[3:]}))
    else:
        await record_until_enter(ws)


async def converse(ws, speaker: Speaker) -> None:
    async for raw in ws:
        if isinstance(raw, bytes):  # question audio
            speaker.feed(raw)
            continue

        msg = json.loads(raw)
        kind = msg["type"]
        if kind == "session.ready":
            print(f"[interview {msg['interview_id']} started]\n")
        elif kind == "question.text":
            print(f"Q{msg['seq']}: {msg['text']}\n")
        elif kind == "question.audio_end":
            await speaker.drain()  # don't open the mic over the question
            await answer(ws)
        elif kind == "transcript.final":
            print(f"  You said: {msg['text']}\n")
        elif kind == "error":
            print(f"[error {msg['code']}: {msg['message']}]")
            if msg["code"] in _RETRY_CODES:
                await answer(ws)
        elif kind == "session.end":
            print(f"[session ended: {msg['reason']}]")
        # turn.complete needs no output


async def main(token: str, url: str) -> None:
    speaker = Speaker()
    speaker.start()
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"type": "session.start", "token": token}))
            try:
                await converse(ws, speaker)
            except websockets.ConnectionClosedError:
                pass  # abnormal close; reported below

            if ws.close_code not in (None, 1000):
                print(f"[closed {ws.close_code}: {ws.close_reason or 'no reason given'}]")
    finally:
        speaker.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    url = sys.argv[2] if len(sys.argv) > 2 else "ws://localhost:8002/v1/ws/interview"
    asyncio.run(main(sys.argv[1], url))
