"""ITv2Server must survive stray clients (port scans, junk) and always stop promptly."""

from __future__ import annotations

import asyncio
import time

import pytest

from dsc_itv2.server import ITv2Server
from dsc_itv2.session import ConnectionSettings

SETTINGS = ConnectionSettings(integration_id="123456789012", type1_access_code="12345678")


async def _start_server() -> ITv2Server:
    server = ITv2Server(SETTINGS, host="127.0.0.1", port=0)
    await server.start()
    return server


@pytest.mark.asyncio
async def test_stop_returns_with_silent_stray_client() -> None:
    """A client that connects and never speaks must not block stop()."""
    server = await _start_server()
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    await asyncio.sleep(0.2)
    t0 = time.monotonic()
    await asyncio.wait_for(server.stop(), timeout=15)
    assert time.monotonic() - t0 < 15
    writer.close()


@pytest.mark.asyncio
async def test_stop_returns_with_junk_client_that_never_reads() -> None:
    """A port-scanner-like client sending junk and never reading must not block stop()."""
    server = await _start_server()
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    writer.write(b"GET / HTTP/1.0\r\nHost: x\r\n\r\n" + b"\x00\xff" * 512)
    await writer.drain()
    await asyncio.sleep(0.3)
    t0 = time.monotonic()
    await asyncio.wait_for(server.stop(), timeout=15)
    assert time.monotonic() - t0 < 15
    writer.close()


@pytest.mark.asyncio
async def test_connection_close_is_bounded() -> None:
    """ITv2Connection.close() finishes even when the peer never reads."""
    server = await _start_server()
    seen: list = []

    async def collect() -> None:
        async for conn in server.connections():
            seen.append(conn)
            return

    task = asyncio.create_task(collect())
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    await asyncio.wait_for(task, timeout=5)
    conn = seen[0]
    t0 = time.monotonic()
    await asyncio.wait_for(conn.close(), timeout=10)
    assert time.monotonic() - t0 < 10
    assert not conn.is_open
    writer.close()
    await server.stop()
