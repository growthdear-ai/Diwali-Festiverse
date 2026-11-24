"""BAND WebSocket listener worker for live agent collaboration.

This module runs as a standalone worker process that maintains a persistent
WebSocket connection to BAND to receive live mentions and room messages.

Run with:
    python -m workers.band_listener

Requires BAND_ENABLED=true and valid agent credentials in .env.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app.core.config import settings
from app.integrations.band_client import (
    BandAgentConfig,
    BandWebSocketListener,
    get_scout_client,
    get_verifier_client,
    get_band_room_id,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


class BandListenerWorker:
    """Manages the BAND WebSocket connection for the Verifier agent."""

    def __init__(self) -> None:
        self._running = False
        self._listener: BandWebSocketListener | None = None
        self._shutdown_event = asyncio.Event()

    async def handle_message(self, data: dict) -> None:
        """Handle incoming BAND WebSocket message.

        This is where you'd process @mentions, human replies, or commands
        to trigger re-verification or other actions.
        """
        logger.info("Received BAND message: %s", data.get("type", "unknown"))

        # Example: Check for mentions of the Verifier agent
        message_text = data.get("text", "") or data.get("content", "")
        if "@Nazar Verifier" in message_text or "@NazarVerifier" in message_text:
            logger.info("Verifier agent mentioned in BAND room")
            # Could trigger a re-verification here

        # Example: Check for Scout-related messages
        if data.get("metadata", {}).get("nazar_type") == "scout_candidate":
            logger.info("Scout candidate message received via WebSocket")

    async def start(self) -> None:
        """Start the WebSocket listener."""
        if not settings.band_enabled:
            logger.warning("BAND_ENABLED=false; listener will not start")
            return

        band_room_id = get_band_room_id()
        if not band_room_id:
            logger.warning("BAND_ROOM_ID not configured; listener will not start")
            return

        verifier_config = BandAgentConfig(
            agent_id=settings.band_verifier_agent_id,
            api_key=settings.band_verifier_api_key,
            name="Nazar Verifier",
        )

        if not verifier_config.agent_id or not verifier_config.api_key:
            logger.warning("Verifier agent credentials not configured; listener will not start")
            return

        self._listener = BandWebSocketListener(
            agent_config=verifier_config,
            room_id=band_room_id,
            on_message_callback=self.handle_message,
        )

        self._running = True
        logger.info("Starting BAND WebSocket listener for Verifier agent...")

        try:
            await self._listener.connect()
            await self._listener.listen()
        except asyncio.CancelledError:
            logger.info("BAND listener cancelled")
        except Exception as exc:
            logger.exception("BAND listener error: %s", exc)
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the WebSocket listener."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping BAND WebSocket listener...")

        if self._listener:
            await self._listener.close()
            self._listener = None

        self._shutdown_event.set()


async def main() -> None:
    """Entry point for the BAND listener worker."""
    worker = BandListenerWorker()

    # Handle shutdown signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(worker.stop()))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await worker.stop()


if __name__ == "__main__":
    if sys.platform == "win32":
        # Windows: use proactor event loop for better subprocess support
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(main())