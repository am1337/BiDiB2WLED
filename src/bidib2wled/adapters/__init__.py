"""BiDiB-Nachrichten und netBiDiB-Framing.

Nachricht: SIZE | ADDR... | MSG_NUM | MSG_TYPE | DATA
Lokale Nachrichten: ADDR=0x00, MSG_NUM=0x00.
TCP (netBiDiB 0.2): kein MAGIC/CRC, Stream aus solchen Nachrichten.

Die lokalen Typnummern folgen der öffentlichen BiDiB-Header-Zuordnung
(Downstream 0x70–0x7F, Upstream 0xF0–0xFF). Gegenstellen, die denselben
Typ in beiden Richtungen nutzen, werden über die 0x80-Variante erkannt.
"""

from __future__ import annotations

from dataclasses import dataclass

# System (downstream)
MSG_SYS_GET_MAGIC = 0x01
MSG_SYS_GET_P_VERSION = 0x02
MSG_SYS_ENABLE = 0x03
MSG_SYS_DISABLE = 0x04
MSG_SYS_GET_UNIQUE_ID = 0x05
MSG_SYS_GET_SW_VERSION = 0x06
MSG_SYS_PING = 0x07
MSG_SYS_IDENTIFY = 0x08
MSG_SYS_RESET = 0x09
MSG_GET_PKT_CAPACITY = 0x0A
MSG_NODETAB_GETALL = 0x0B
MSG_NODETAB_GETNEXT = 0x0C
MSG_NODE_CHANGED_ACK = 0x0D
MSG_SYS_GET_ERROR = 0x0E

MSG_FEATURE_GETALL = 0x10
MSG_FEATURE_GETNEXT = 0x11
MSG_FEATURE_GET = 0x12
MSG_FEATURE_SET = 0x13
MSG_SYS_CLOCK = 0x18
MSG_STRING_GET = 0x19
MSG_STRING_SET = 0x1A

MSG_ACCESSORY_SET = 0x38
MSG_ACCESSORY_GET = 0x39
MSG_ACCESSORY_PARA_SET = 0x3A
MSG_ACCESSORY_PARA_GET = 0x3B

# System (upstream)
MSG_SYS_MAGIC = 0x81
MSG_SYS_PONG = 0x82
MSG_SYS_P_VERSION = 0x83
MSG_SYS_UNIQUE_ID = 0x84
MSG_SYS_SW_VERSION = 0x85
MSG_SYS_ERROR = 0x86
MSG_SYS_IDENTIFY_STATE = 0x87
MSG_NODETAB_COUNT = 0x88
MSG_NODETAB = 0x89
MSG_PKT_CAPACITY = 0x8A
MSG_NODE_NA = 0x8B
MSG_STALL = 0x8E

MSG_FEATURE = 0x90
MSG_FEATURE_NA = 0x91
MSG_FEATURE_COUNT = 0x92
MSG_STRING = 0x95

MSG_ACCESSORY_STATE = 0xB8
MSG_ACCESSORY_PARA = 0xB9
MSG_ACCESSORY_NOTIFY = 0xBA

# Local
MSG_LOCAL_LOGON_ACK = 0x70
MSG_LOCAL_PING = 0x71
MSG_LOCAL_LOGON_REJECTED = 0x72
MSG_LOCAL_SYNC = 0x74
MSG_LOCAL_DISCOVER = 0x75
MSG_LOCAL_LINK_DOWN = 0x7F
MSG_LOCAL_PROTOCOL_SIGNATURE_DOWN = 0x7E
MSG_LOCAL_LOGON = 0xF0
MSG_LOCAL_PONG = 0xF1
MSG_LOCAL_LOGOFF = 0xF2
MSG_LOCAL_ANNOUNCE = 0xF3
MSG_LOCAL_LINK_UP = 0xFF
MSG_LOCAL_PROTOCOL_SIGNATURE_UP = 0xFE
# ältere Stacks nutzten 0x7D/0xFD für LINK
MSG_LOCAL_LINK_DOWN_LEGACY = 0x7D
MSG_LOCAL_LINK_UP_LEGACY = 0xFD

# Rocrail sendet Signatur/LINK mit den Upstream-Nummern in beide Richtungen.
MSG_LOCAL_LINK = MSG_LOCAL_LINK_UP
MSG_LOCAL_PROTOCOL_SIGNATURE = MSG_LOCAL_PROTOCOL_SIGNATURE_UP

BIDIB_LINK_DESCRIPTOR_PROD_STRING = 0x00
BIDIB_LINK_DESCRIPTOR_USER_STRING = 0x01
BIDIB_LINK_DESCRIPTOR_ROLE = 0x7F
BIDIB_LINK_DESCRIPTOR_P_VERSION = 0x80
BIDIB_LINK_NODE_UNAVAILABLE = 0x81
BIDIB_LINK_NODE_AVAILABLE = 0x82
BIDIB_LINK_PAIRING_REQUEST = 0xFC
BIDIB_LINK_STATUS_UNPAIRED = 0xFD
BIDIB_LINK_STATUS_PAIRED = 0xFE
BIDIB_LINK_DESCRIPTOR_UID = 0xFF

BIDIB_ROLE_INTERFACE = 0x01
BIDIB_ROLE_NODE = 0x02

BIDIB_SYS_MAGIC = 0xAFFE
BIDIB_BOOT_MAGIC = 0xB00D

FEATURE_ACCESSORY_COUNT = 40
FEATURE_ACCESSORY_SURVEILLED = 41
FEATURE_STRING_SIZE = 252
FEATURE_RELEVANT_PID_BITS = 253

BIDIB_ACC_STATE_DONE = 0x00
BIDIB_ACC_STATE_WAIT = 0x01
BIDIB_ACC_STATE_ERROR = 0x80
BIDIB_ACC_STATE_ERROR_VOID = 0x01

BIDIB_ACCESSORY_PARA_NOTEXIST = 255

PROTO_VERSION = (8, 0)  # proto-ver_l, proto-ver_h → 0.8
SW_VERSION = (0, 1, 0)  # l, h, u → 0, 1, 0 for 0.1.0? "1:sw-ver_l, 2:sw-ver_h, 3:sw-ver_u" typically 0.1.0 → 0, 1, 0 wait
# Common encoding: major in u, minor in h, patch in l → 1.0.0 = 0, 0, 1
# We'll send 0.1.0 as l=0, h=1, u=0 matching "0.1.0" display in some tools as 0.1.0

SIGNATURE_TEXT = b"BiDiB2WLED"


def is_local_type(msg_type: int) -> bool:
    low = msg_type & 0x7F
    return 0x70 <= low <= 0x7F


def is_signature_type(msg_type: int) -> bool:
    return (msg_type & 0x7F) == 0x7E


def is_link_type(msg_type: int) -> bool:
    return (msg_type & 0x7F) in (0x7D, 0x7F)


def canonical_local(msg_type: int) -> int:
    """Map upstream/downstream local types onto the downstream number."""
    if msg_type >= 0x80 and is_local_type(msg_type):
        return msg_type & 0x7F
    return msg_type


@dataclass
class BidibMessage:
    msg_type: int
    data: bytes = b""
    addr: bytes = b"\x00"
    seq: int = 0

    @property
    def local_type(self) -> int:
        return canonical_local(self.msg_type)


def encode_message(message: BidibMessage) -> bytes:
    addr = message.addr or b"\x00"
    body = addr + bytes([message.seq & 0xFF, message.msg_type & 0xFF]) + message.data
    if len(body) > 127:
        raise ValueError("BiDiB-Nachricht zu lang")
    return bytes([len(body)]) + body


def encode_local(msg_type: int, data: bytes = b"") -> bytes:
    return encode_message(BidibMessage(msg_type=msg_type, data=data, addr=b"\x00", seq=0))


def encode_signature(brand: bytes = SIGNATURE_TEXT) -> bytes:
    if not brand.startswith(b"BiDiB"):
        brand = b"BiDiB" + brand
    return encode_local(MSG_LOCAL_PROTOCOL_SIGNATURE, brand)


class MessageDecoder:
    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[BidibMessage]:
        self._buf.extend(chunk)
        out: list[BidibMessage] = []
        while True:
            msg = self._pop()
            if msg is None:
                break
            out.append(msg)
        return out

    def _pop(self) -> BidibMessage | None:
        while self._buf:
            size = self._buf[0]
            if size < 3 or size > 127:
                del self._buf[0]
                continue
            if len(self._buf) < 1 + size:
                return None
            raw = bytes(self._buf[1 : 1 + size])
            del self._buf[: 1 + size]
            if raw[0] == 0x00:
                addr = b"\x00"
                rest = raw[1:]
            else:
                end = raw.find(b"\x00")
                if end < 0:
                    continue
                addr = raw[: end + 1]
                rest = raw[end + 1 :]
            if len(rest) < 2:
                continue
            seq, msg_type = rest[0], rest[1]
            return BidibMessage(msg_type=msg_type, data=rest[2:], addr=addr, seq=seq)
        return None


def unescape_serial(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 0xFD and i + 1 < len(data):
            out.append(data[i + 1] ^ 0x20)
            i += 2
        else:
            out.append(data[i])
            i += 1
    return bytes(out)


class SerialPacketDecoder:
    """MAGIC-framed serial packets (0xFE … 0xFE) → BiDiB-Nachrichten."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._inner = MessageDecoder()

    def feed(self, chunk: bytes) -> list[BidibMessage]:
        self._buf.extend(chunk)
        out: list[BidibMessage] = []
        while True:
            packet = self._pop_packet()
            if packet is None:
                break
            if len(packet) < 2:
                continue
            out.extend(self._inner.feed(packet[:-1]))
        return out

    def _pop_packet(self) -> bytes | None:
        while self._buf and self._buf[0] != 0xFE:
            del self._buf[0]
        if len(self._buf) < 2:
            return None
        end = self._buf.find(0xFE, 1)
        if end < 0:
            return None
        raw = bytes(self._buf[1:end])
        del self._buf[: end + 1]
        return unescape_serial(raw)


def find_descriptor_uid(data: bytes) -> bytes | None:
    """UID aus MSG_LOCAL_LINK DESCRIPTOR_UID, auch bei kaputtem Framing."""
    for typ in (
        MSG_LOCAL_LINK_DOWN,
        MSG_LOCAL_LINK_UP,
        MSG_LOCAL_LINK_DOWN_LEGACY,
        MSG_LOCAL_LINK_UP_LEGACY,
    ):
        needle = bytes([0x00, 0x00, typ, BIDIB_LINK_DESCRIPTOR_UID])
        pos = 0
        while True:
            idx = data.find(needle, pos)
            if idx < 0:
                break
            start = idx + 4
            if start + 7 <= len(data):
                return data[start : start + 7]
            pos = idx + 1
    return None


def uid_from_hex(text: str) -> bytes:
    cleaned = text.strip().lower().replace(":", "").replace(" ", "")
    data = bytes.fromhex(cleaned)
    if len(data) != 7:
        raise ValueError("Unique-ID muss 7 Byte (14 Hex-Zeichen) sein")
    return data


def uid_to_hex(uid: bytes) -> str:
    return uid.hex()


def generate_uid(serial: int | None = None) -> bytes:
    import os

    if serial is None:
        serial = int.from_bytes(os.urandom(2), "little")
    product = 0x2B01  # frei gewählte Produktkennung für BiDiB2WLED
    return bytes(
        [
            0x04,  # class: accessory
            0x00,  # classx
            0x00,  # VID 0 = virtueller Software-Knoten
            product & 0xFF,
            (product >> 8) & 0xFF,
            serial & 0xFF,
            (serial >> 8) & 0xFF,
        ]
    )


def encode_iso_string(text: str, max_len: int = 24) -> bytes:
    encoded = text.encode("latin-1", errors="replace")[:max_len]
    return bytes([len(encoded)]) + encoded
