"""Unit tests for the Port 37777 NetSDK DVR2 (0xa0) + JSON-RPC (0xf6) protocol."""

from __future__ import annotations

import asyncio
import json
import struct
import pytest

from aio_dahua_h5a.exceptions import DahuaAuthError, DahuaRpcError
from aio_dahua_h5a.models import CameraEvent
from aio_dahua_h5a.protocol import (
    CMD_JSON_RPC,
    CMD_LOGIN_REQ,
    CMD_LOGIN_RESP,
    HEADER_LEN,
    DahuaNetSdkProtocolClient,
    build_f6_rpc_packet,
    build_step1_challenge_packet,
    build_step2_login_packet,
    compute_dvr2_digest,
    dh_superencipherment,
    md5_hex_upper,
    parse_step1_challenge_response,
)


def test_dh_superencipherment_deterministic() -> None:
    """Verify DH_Superencipherment produces an 8-char Base62 hash matching SDK behavior."""
    token = dh_superencipherment("unit_test_password_example")
    assert len(token) == 8
    assert token.isalnum()
    # Deterministic check
    assert dh_superencipherment("admin123") == "Ny2SRZzv"


def test_compute_dvr2_digest_structure() -> None:
    """Verify dual MD5 + DH_Superencipherment token is 64 uppercase hex chars."""
    digest = compute_dvr2_digest(
        username="admin",
        password="unit_test_password_example",
        realm="Login to TESTREALM1234",
        random_challenge="1938475610",
    )
    assert len(digest) == 64
    assert digest == digest.upper()
    int(digest, 16)  # Valid hex


def test_step1_and_step2_packet_framing() -> None:
    """Verify Step 1 challenge request/response and Step 2 login packet layout."""
    pkt1 = build_step1_challenge_packet()
    assert len(pkt1) == HEADER_LEN
    assert pkt1[0] == CMD_LOGIN_REQ
    assert pkt1[0:4] == b"\xa0\x05\x00\x60"
    assert pkt1[24:32] == b"\x01\x02\x00\x01\x3c\x00\xa1\xaa"

    ext1 = b"Realm:Login to FF8A7CD1282D3D39\r\nRandom:2112708297\r\n\r\n"
    resp1_hdr = bytearray(HEADER_LEN)
    resp1_hdr[0] = CMD_LOGIN_RESP
    struct.pack_into("<I", resp1_hdr, 4, len(ext1))
    realm, rnd = parse_step1_challenge_response(bytes(resp1_hdr) + ext1)
    assert realm == "Login to FF8A7CD1282D3D39"
    assert rnd == "2112708297"

    pkt2 = build_step2_login_packet("admin", "A" * 64)
    assert pkt2[0:4] == b"\xa0\x05\x00\x60"
    assert pkt2[24:32] == b"\x01\x02\x00\x08\x00\x00\xa1\xaa"
    ext2_len = struct.unpack("<I", pkt2[4:8])[0]
    assert ext2_len == len(b"admin&&" + b"A" * 64)
    assert pkt2[32:] == b"admin&&" + b"A" * 64


def test_build_f6_rpc_packet_framing() -> None:
    """Verify 0xf6 JSON-RPC request framing on the main connection (no 4-byte prefix)."""
    payload = {
        "method": "magicBox.getDeviceType",
        "params": None,
        "id": 256,
        "session": 1005,
    }
    frame = build_f6_rpc_packet(1005, 256, payload)
    hdr = frame[:HEADER_LEN]
    body = frame[HEADER_LEN:]

    assert hdr[0] == CMD_JSON_RPC
    ext_len = struct.unpack("<I", hdr[4:8])[0]
    req_id = struct.unpack("<I", hdr[8:12])[0]
    total_len = struct.unpack("<I", hdr[16:20])[0]
    sess_id = struct.unpack("<I", hdr[24:28])[0]

    assert ext_len == len(body)
    assert total_len == len(body)
    assert req_id == 256
    assert sess_id == 1005
    assert body.endswith(b"\n\x00")
    parsed = json.loads(body[:-2].decode("utf-8"))
    assert parsed == payload


@pytest.mark.asyncio
async def test_protocol_client_login_fragmented_rpc_and_events() -> None:
    """Test full async login, multi-chunk 0xf6 response reassembly, and event push."""
    expected_session = 4242

    async def handle_client(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            # Step 1
            req1 = await reader.readexactly(HEADER_LEN)
            assert req1[0] == CMD_LOGIN_REQ
            ext1 = b"Realm:Login to MOCKCAM\r\nRandom:987654321\r\n\r\n"
            rhdr1 = bytearray(HEADER_LEN)
            rhdr1[0] = CMD_LOGIN_RESP
            struct.pack_into("<I", rhdr1, 4, len(ext1))
            writer.write(bytes(rhdr1) + ext1)
            await writer.drain()

            # Step 2
            req2_hdr = await reader.readexactly(HEADER_LEN)
            ext2_len = struct.unpack("<I", req2_hdr[4:8])[0]
            ext2 = await reader.readexactly(ext2_len)
            expected_tok = compute_dvr2_digest(
                "admin", "mock_pass", "Login to MOCKCAM", "987654321"
            )
            if ext2 != f"admin&&{expected_tok}".encode("utf-8"):
                rhdr2 = bytearray(HEADER_LEN)
                rhdr2[0] = CMD_LOGIN_RESP
                rhdr2[8] = 1
                rhdr2[9] = 2  # invalid password
                writer.write(bytes(rhdr2))
                await writer.drain()
                return

            rhdr2 = bytearray(HEADER_LEN)
            rhdr2[0] = CMD_LOGIN_RESP
            rhdr2[8] = 0
            struct.pack_into("<I", rhdr2, 16, expected_session)
            writer.write(bytes(rhdr2))
            await writer.drain()

            # Process 0xf6 RPC requests
            while True:
                hdr = await reader.readexactly(HEADER_LEN)
                blen = struct.unpack("<I", hdr[4:8])[0]
                req_id = struct.unpack("<I", hdr[8:12])[0]
                body = await reader.readexactly(blen)
                req = json.loads(body.rstrip(b"\x00\r\n").decode("utf-8"))
                method = req["method"]

                if method == "global.logout":
                    resp_bytes = (
                        json.dumps({"result": True, "id": req_id, "session": expected_session}).encode("utf-8")
                        + b"\n\x00"
                    )
                    ohdr = bytearray(HEADER_LEN)
                    ohdr[0] = CMD_JSON_RPC
                    struct.pack_into("<I", ohdr, 4, len(resp_bytes))
                    struct.pack_into("<I", ohdr, 8, req_id)
                    struct.pack_into("<I", ohdr, 16, len(resp_bytes))
                    struct.pack_into("<I", ohdr, 24, expected_session)
                    writer.write(bytes(ohdr) + resp_bytes)
                    await writer.drain()
                    break

                # Simulate a 2-chunk fragmented 0xf6 response
                full_resp = (
                    json.dumps(
                        {
                            "result": True,
                            "params": {"table": [{"Enable": True, "Status": False}]},
                            "id": req_id,
                            "session": expected_session,
                        }
                    ).encode("utf-8")
                    + b"\n\x00"
                )
                mid = len(full_resp) // 2
                part1, part2 = full_resp[:mid], full_resp[mid:]

                for part in (part1, part2):
                    chdr = bytearray(HEADER_LEN)
                    chdr[0] = CMD_JSON_RPC
                    struct.pack_into("<I", chdr, 4, len(part))
                    struct.pack_into("<I", chdr, 8, req_id)
                    struct.pack_into("<I", chdr, 16, len(full_resp))
                    struct.pack_into("<I", chdr, 24, expected_session)
                    writer.write(bytes(chdr) + part)
                await writer.drain()

                # Also push an unsolicited event stream frame
                ev_bytes = (
                    json.dumps(
                        {
                            "method": "client.notifyEventStream",
                            "params": {
                                "SID": 99,
                                "eventList": [
                                    {
                                        "Code": "SmartMotionHuman",
                                        "Action": "Start",
                                        "Index": 0,
                                        "Data": {"Channel": 0},
                                    }
                                ],
                            },
                            "id": 0,
                            "session": expected_session,
                        }
                    ).encode("utf-8")
                    + b"\n\x00"
                )
                ehdr = bytearray(HEADER_LEN)
                ehdr[0] = CMD_JSON_RPC
                struct.pack_into("<I", ehdr, 4, len(ev_bytes))
                struct.pack_into("<I", ehdr, 8, 0)
                struct.pack_into("<I", ehdr, 16, len(ev_bytes))
                struct.pack_into("<I", ehdr, 24, expected_session)
                writer.write(bytes(ehdr) + ev_bytes)
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    received_events: list[CameraEvent] = []

    async with server:
        # 1. Verify invalid password raises DahuaAuthError
        bad_client = DahuaNetSdkProtocolClient("127.0.0.1", "admin", "wrong_pass", port=port)
        with pytest.raises(DahuaAuthError):
            await bad_client.connect()

        # 2. Verify valid login, fragmented response reassembly, and event callback
        client = DahuaNetSdkProtocolClient("127.0.0.1", "admin", "mock_pass", port=port)
        client.register_event_callback(received_events.append)
        sid = await client.connect()
        assert sid == expected_session

        resp = await client.rpc("configManager.getConfig", {"name": "AELensMask"})
        assert resp["result"] is True
        assert resp["params"]["table"][0]["Status"] is False

        await asyncio.sleep(0.05)
        assert len(received_events) == 1
        assert received_events[0].code == "SmartMotionHuman"
        assert received_events[0].action == "Start"

        await client.close()
