"""Asyncio implementation of the Dahua Port 37777 NetSDK DVR2 (0xa0) + JSON-RPC (0xf6) protocol."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import struct
from collections.abc import Callable
from typing import Any

from .exceptions import DahuaAuthError, DahuaConnectionError, DahuaRpcError
from .models import CameraEvent

_LOGGER = logging.getLogger(__name__)

CHARSET_BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
HEADER_LEN = 32
CMD_LOGIN_REQ = 0xA0
CMD_LOGIN_RESP = 0xB0
CMD_JSON_RPC = 0xF6


def dh_superencipherment(password: str) -> str:
    """Compute Dahua's 8-character Base62 'Superencipherment' password hash.

    Reconstructed from `DH_Superencipherment` in `libdhnetsdk.so` / `libnetsdk.so`:
    1. Compute 16-byte raw MD5 digest of the UTF-8 password.
    2. For each of the 8 byte-pairs (2*i, 2*i+1), take `(b0 + b1) % 62`
       and index into `0-9A-Za-z`.
    """
    md5_bytes = hashlib.md5(password.encode("utf-8")).digest()
    return "".join(
        CHARSET_BASE62[(md5_bytes[2 * i] + md5_bytes[2 * i + 1]) % 62]
        for i in range(8)
    )


def md5_hex_upper(value: str) -> str:
    """Return uppercase 32-character hexadecimal MD5 digest of `value`."""
    return hashlib.md5(value.encode("utf-8")).hexdigest().upper()


def compute_dvr2_digest(
    username: str,
    password: str,
    realm: str,
    random_challenge: str,
) -> str:
    """Compute the 64-character dual digest token (`H1 + H2`) for Step 2 login.

    - `A1 = MD5_UPPER(f"{username}:{realm}:{password}")`
    - `H1 = MD5_UPPER(f"{username}:{random_challenge}:{A1}")`
    - `dh_pwd = dh_superencipherment(password)`
    - `H2 = MD5_UPPER(f"{username}:{random_challenge}:{dh_pwd}")`
    - Token sent in `ext2` is `f"{username}&&{H1}{H2}"`.
    """
    a1 = md5_hex_upper(f"{username}:{realm}:{password}")
    h1 = md5_hex_upper(f"{username}:{random_challenge}:{a1}")
    dh_pwd = dh_superencipherment(password)
    h2 = md5_hex_upper(f"{username}:{random_challenge}:{dh_pwd}")
    return f"{h1}{h2}"


def build_step1_challenge_packet() -> bytes:
    """Construct the 32-byte Step 1 `0xa0` Digest challenge request packet."""
    pkt = bytearray(HEADER_LEN)
    pkt[0:4] = b"\xa0\x05\x00\x60"
    pkt[24:32] = b"\x01\x02\x00\x01\x3c\x00\xa1\xaa"
    return bytes(pkt)


def parse_step1_challenge_response(packet: bytes) -> tuple[str, str]:
    """Parse `Realm` and `Random` challenge strings from a Step 1 `0xb0` response."""
    if len(packet) < HEADER_LEN or packet[0] != CMD_LOGIN_RESP:
        raise DahuaAuthError(
            f"Unexpected Step 1 response header: {packet[:HEADER_LEN].hex()}"
        )
    ext_text = packet[HEADER_LEN:].decode("utf-8", errors="replace")
    realm = ""
    random_challenge = ""
    for line in ext_text.splitlines():
        if line.startswith("Realm:"):
            realm = line.split(":", 1)[1].strip()
        elif line.startswith("Random:"):
            random_challenge = line.split(":", 1)[1].strip()
    if not realm or not random_challenge:
        raise DahuaAuthError(
            f"Missing Realm or Random in Step 1 challenge: {ext_text!r}"
        )
    return realm, random_challenge


def build_step2_login_packet(username: str, digest_token: str) -> bytes:
    """Construct the Step 2 `0xa0` Digest login request packet (`header + ext2`)."""
    ext2 = f"{username}&&{digest_token}".encode("utf-8")
    pkt = bytearray(HEADER_LEN)
    pkt[0:4] = b"\xa0\x05\x00\x60"
    struct.pack_into("<I", pkt, 4, len(ext2))
    pkt[24:32] = b"\x01\x02\x00\x08\x00\x00\xa1\xaa"
    return bytes(pkt) + ext2


def build_f6_rpc_packet(
    session_id: int,
    req_id: int,
    payload: dict[str, Any],
) -> bytes:
    """Construct a `0xf6` JSON-RPC request frame on the main NetSDK connection.

    Reconstructed from `sendJsonPacket_dvr2` in `libdhnetsdk.so`:
    - On the main connection (`subconn_id == -1`), no 4-byte prefix precedes the JSON.
    - `hdr[0] = 0xf6`
    - `hdr[4:8] = uint32_le(len(json_bytes))`
    - `hdr[8:12] = uint32_le(req_id)`
    - `hdr[16:20] = uint32_le(len(json_bytes))`
    - `hdr[24:28] = uint32_le(session_id)`
    """
    json_bytes = (
        json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n\x00"
    )
    hdr = bytearray(HEADER_LEN)
    hdr[0] = CMD_JSON_RPC
    struct.pack_into("<I", hdr, 4, len(json_bytes))
    struct.pack_into("<I", hdr, 8, req_id)
    struct.pack_into("<I", hdr, 16, len(json_bytes))
    struct.pack_into("<I", hdr, 24, session_id)
    return bytes(hdr) + json_bytes


class DahuaNetSdkProtocolClient:
    """Low-level async client for Port 37777 DVR2 Login + JSON-RPC (`0xf6`)."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 37777,
        timeout: float = 8.0,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._session_id: int = 0
        self._seq_id: int = 1
        self._write_lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._event_callbacks: list[Callable[[CameraEvent], Any]] = []
        self._attached_sid: int | None = None

    @property
    def session_id(self) -> int:
        return self._session_id

    @property
    def connected(self) -> bool:
        return (
            self._writer is not None
            and not self._writer.is_closing()
            and self._session_id != 0
        )

    @property
    def is_connected(self) -> bool:
        return self.connected

    def register_event_callback(
        self, callback: Callable[[CameraEvent], Any]
    ) -> Callable[[], None]:
        """Register a callback invoked on incoming `client.notifyEventStream` events."""
        self._event_callbacks.append(callback)

        def _remove() -> None:
            if callback in self._event_callbacks:
                self._event_callbacks.remove(callback)

        return _remove

    async def connect(self) -> int:
        """Establish TCP connection and complete 2-step `0xa0` Digest authentication."""
        async with self._connect_lock:
            if self.connected:
                return self._session_id

            await self._cleanup_transport()

            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=self.timeout,
                )
            except (OSError, asyncio.TimeoutError) as err:
                raise DahuaConnectionError(
                    f"Failed to connect to {self.host}:{self.port}: {err}"
                ) from err

            try:
                # Step 1: Request Digest challenge
                writer.write(build_step1_challenge_packet())
                await writer.drain()

                hdr1 = await asyncio.wait_for(
                    reader.readexactly(HEADER_LEN), timeout=self.timeout
                )
                ext1_len = struct.unpack("<I", hdr1[4:8])[0]
                ext1 = (
                    await asyncio.wait_for(
                        reader.readexactly(ext1_len), timeout=self.timeout
                    )
                    if ext1_len > 0
                    else b""
                )
                realm, random_challenge = parse_step1_challenge_response(hdr1 + ext1)

                # Step 2: Send dual-hash digest credentials
                digest_token = compute_dvr2_digest(
                    self.username, self.password, realm, random_challenge
                )
                writer.write(build_step2_login_packet(self.username, digest_token))
                await writer.drain()

                hdr2 = await asyncio.wait_for(
                    reader.readexactly(HEADER_LEN), timeout=self.timeout
                )
                ext2_len = struct.unpack("<I", hdr2[4:8])[0]
                if ext2_len > 0:
                    await asyncio.wait_for(
                        reader.readexactly(ext2_len), timeout=self.timeout
                    )

                if hdr2[0] != CMD_LOGIN_RESP:
                    raise DahuaAuthError(
                        f"Unexpected Step 2 response command: 0x{hdr2[0]:02x}"
                    )

                login_result = hdr2[8]
                err_subcode = hdr2[9]
                if login_result != 0:
                    raise DahuaAuthError(
                        f"Dahua login failed (status={login_result}, error_code={err_subcode})",
                        error_code=err_subcode,
                    )

                session_id = struct.unpack("<I", hdr2[16:20])[0]
                if session_id == 0:
                    raise DahuaAuthError("Camera returned zero session_id")

                self._reader = reader
                self._writer = writer
                self._session_id = session_id
                self._reader_task = asyncio.create_task(
                    self._reader_loop(), name=f"dahua-h5a-reader-{self.host}"
                )
                self._keepalive_task = asyncio.create_task(
                    self._keepalive_loop(), name=f"dahua-h5a-keepalive-{self.host}"
                )
                return session_id
            except Exception:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
                raise

    async def close(self) -> None:
        """Gracefully log out and close the TCP connection."""
        async with self._connect_lock:
            if self.connected:
                with contextlib.suppress(Exception):
                    await self.rpc("global.logout", None, reconnect=False)
            await self._cleanup_transport()

    async def _cleanup_transport(self) -> None:
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._keepalive_task
            self._keepalive_task = None

        if self._reader_task is not None:
            if self._reader_task is not asyncio.current_task():
                self._reader_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._reader_task
            self._reader_task = None

        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None

        self._reader = None
        self._session_id = 0
        self._attached_sid = None

        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(DahuaConnectionError("Connection closed"))
        self._pending.clear()

    async def _keepalive_loop(self) -> None:
        """Send periodic `global.keepAlive` heartbeats to keep the session alive."""
        while self.connected:
            await asyncio.sleep(25.0)
            if not self.connected:
                break
            try:
                await self.rpc(
                    "global.keepAlive",
                    {"timeout": 60, "active": False},
                    reconnect=False,
                )
            except Exception as err:
                _LOGGER.debug("KeepAlive failed on %s: %s", self.host, err)
                break

    async def _reader_loop(self) -> None:
        """Continuously read 32-byte NetSDK frames, reassembling fragmented `0xf6` payloads."""
        reader = self._reader
        if reader is None:
            return

        reassembly_buffers: dict[int, bytearray] = {}
        reassembly_totals: dict[int, int] = {}

        try:
            while True:
                hdr = await reader.readexactly(HEADER_LEN)
                cmd = hdr[0]
                chunk_len = struct.unpack("<I", hdr[4:8])[0]
                req_id = struct.unpack("<I", hdr[8:12])[0]
                total_len = struct.unpack("<I", hdr[16:20])[0]

                chunk = (
                    await reader.readexactly(chunk_len) if chunk_len > 0 else b""
                )

                if cmd != CMD_JSON_RPC:
                    _LOGGER.debug(
                        "Ignoring non-0xf6 frame cmd=0x%02x len=%d", cmd, chunk_len
                    )
                    continue

                buf = reassembly_buffers.setdefault(req_id, bytearray())
                if req_id not in reassembly_totals:
                    reassembly_totals[req_id] = max(total_len, chunk_len)
                buf.extend(chunk)

                if len(buf) >= reassembly_totals[req_id]:
                    raw_bytes = bytes(reassembly_buffers.pop(req_id))
                    reassembly_totals.pop(req_id, None)
                    self._handle_complete_json_frame(req_id, raw_bytes)
        except asyncio.CancelledError:
            raise
        except (asyncio.IncompleteReadError, OSError) as err:
            _LOGGER.debug("Reader loop ended for %s: %s", self.host, err)
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(
                        DahuaConnectionError(f"Connection lost: {err}")
                    )
            self._pending.clear()
            self._session_id = 0

    def _handle_complete_json_frame(self, req_id: int, raw_bytes: bytes) -> None:
        text = raw_bytes.rstrip(b"\x00\r\n").decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"result": False, "error": f"Invalid JSON payload: {text[:200]}"}

        # Check if this is an unsolicited event stream notification
        if isinstance(data, dict) and data.get("method") == "client.notifyEventStream":
            self._dispatch_event_stream(data.get("params") or {})
            return

        fut = self._pending.pop(req_id, None)
        if fut is not None and not fut.done():
            fut.set_result(data)

    def _dispatch_event_stream(self, params: dict[str, Any]) -> None:
        event_list = params.get("eventList") or []
        for item in event_list:
            if not isinstance(item, dict):
                continue
            event = CameraEvent(
                code=str(item.get("Code", "")),
                action=str(item.get("Action", "")),
                index=int(item.get("Index", 0)),
                data=item.get("Data") if isinstance(item.get("Data"), dict) else {},
            )
            for callback in list(self._event_callbacks):
                try:
                    res = callback(event)
                    if asyncio.iscoroutine(res):
                        asyncio.create_task(res)
                except Exception as err:
                    _LOGGER.warning("Error in camera event callback: %s", err)

    async def rpc(
        self,
        method: str,
        params: Any = None,
        *,
        object_id: int | None = None,
        raise_on_error: bool = False,
        reconnect: bool = True,
    ) -> dict[str, Any]:
        """Send a `0xf6` JSON-RPC call and await its reassembled JSON response."""
        if not self.connected:
            if not reconnect:
                raise DahuaConnectionError("Not connected to camera")
            await self.connect()

        async with self._write_lock:
            req_id = self._seq_id << 8
            self._seq_id = (self._seq_id + 1) & 0xFFFFFF
            if self._seq_id == 0:
                self._seq_id = 1

            payload: dict[str, Any] = {
                "method": method,
                "params": params,
                "id": req_id,
                "session": self._session_id,
            }
            if object_id is not None:
                payload["object"] = object_id

            loop = asyncio.get_running_loop()
            fut: asyncio.Future[dict[str, Any]] = loop.create_future()
            self._pending[req_id] = fut

            frame = build_f6_rpc_packet(self._session_id, req_id, payload)
            assert self._writer is not None
            try:
                self._writer.write(frame)
                await self._writer.drain()
            except OSError as err:
                self._pending.pop(req_id, None)
                self._session_id = 0
                raise DahuaConnectionError(
                    f"Socket write failed during {method}: {err}"
                ) from err

        try:
            resp = await asyncio.wait_for(fut, timeout=self.timeout)
        except asyncio.TimeoutError as err:
            self._pending.pop(req_id, None)
            raise DahuaConnectionError(
                f"RPC call '{method}' timed out after {self.timeout}s"
            ) from err

        if raise_on_error and not resp.get("result"):
            raise DahuaRpcError(method, resp.get("error"), resp)

        return resp

    async def attach_events(self, codes: list[str] | None = None) -> int:
        """Subscribe to real-time camera events via `eventManager.attach`."""
        resp = await self.rpc(
            "eventManager.attach",
            {"codes": codes or ["All"]},
            raise_on_error=True,
        )
        sid = int((resp.get("params") or {}).get("SID", 0))
        self._attached_sid = sid
        return sid
