"""Terminal client for the text-mode interview (decision 039).

Stands in for the frontend until it exists:

    uv run python scripts/interview_cli.py <session_token> [ws://localhost:8002/v1/ws/interview]

Get a token from Core API's POST /v1/interviews. Type an answer and press
Enter; type /end to finish early.
"""

from __future__ import annotations

import asyncio
import json
import sys

import websockets


async def main(token: str, url: str) -> None:
    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({"type": "session.start", "token": token}))
        try:
            await converse(ws)
        except websockets.ConnectionClosedError:
            pass  # abnormal close; reported below

        if ws.close_code not in (None, 1000):
            print(f"[closed {ws.close_code}: {ws.close_reason or 'no reason given'}]")


async def converse(ws) -> None:
    loop = asyncio.get_running_loop()
    async for raw in ws:
        msg = json.loads(raw)
        kind = msg["type"]

        if kind == "session.ready":
            print(f"[interview {msg['interview_id']} started]\n")
        elif kind == "question.text":
            print(f"Q{msg['seq']}: {msg['text']}\n")
            try:
                answer = await loop.run_in_executor(None, input, "> ")
            except EOFError:  # stdin closed: end politely
                answer = "/end"
            if answer.strip() == "/end":
                await ws.send(json.dumps({"type": "session.end"}))
            else:
                await ws.send(json.dumps({"type": "answer.text", "text": answer}))
            print()
        elif kind == "error":
            print(f"[error {msg['code']}: {msg['message']}]")
        elif kind == "session.end":
            print(f"[session ended: {msg['reason']}]")
        # turn.complete needs no output


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    url = sys.argv[2] if len(sys.argv) > 2 else "ws://localhost:8002/v1/ws/interview"
    asyncio.run(main(sys.argv[1], url))
