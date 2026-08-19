"""netBiDiB-Knoten: Server (Standard), Pairing, Accessories."""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from dataclasses import dataclass, field

from bidib2wled.adapters import (
    BIDIB_ACC_STATE_DONE,
    BIDIB_ACC_STATE_ERROR,
    BIDIB_ACC_STATE_ERROR_VOID,
    BIDIB_ACC_STATE_WAIT,
    BIDIB_ACCESSORY_PARA_NOTEXIST,
    BIDIB_LINK_DESCRIPTOR_P_VERSION,
    BIDIB_LINK_DESCRIPTOR_PROD_STRING,
    BIDIB_LINK_DESCRIPTOR_ROLE,
    BIDIB_LINK_DESCRIPTOR_UID,
    BIDIB_LINK_DESCRIPTOR_USER_STRING,
    BIDIB_LINK_NODE_AVAILABLE,
    BIDIB_LINK_PAIRING_REQUEST,
    BIDIB_LINK_STATUS_PAIRED,
    BIDIB_LINK_STATUS_UNPAIRED,
    BIDIB_ROLE_NODE,
    BIDIB_SYS_MAGIC,
    FEATURE_ACCESSORY_COUNT,
    FEATURE_ACCESSORY_SURVEILLED,
    FEATURE_RELEVANT_PID_BITS,
    FEATURE_STRING_SIZE,
    MSG_ACCESSORY_GET,
    MSG_ACCESSORY_NOTIFY,
    MSG_ACCESSORY_PARA,
    MSG_ACCESSORY_PARA_GET,
    MSG_ACCESSORY_SET,
    MSG_ACCESSORY_STATE,
    MSG_FEATURE,
    MSG_FEATURE_COUNT,
    MSG_FEATURE_GET,
    MSG_FEATURE_GETALL,
    MSG_FEATURE_GETNEXT,
    MSG_FEATURE_NA,
    MSG_FEATURE_SET,
    MSG_GET_PKT_CAPACITY,
    MSG_LOCAL_LINK,
    MSG_LOCAL_LINK_DOWN,
    MSG_LOCAL_LINK_UP,
    MSG_LOCAL_LOGOFF,
    MSG_LOCAL_LOGON,
    MSG_LOCAL_LOGON_ACK,
    MSG_LOCAL_LOGON_REJECTED,
    MSG_LOCAL_PING,
    MSG_LOCAL_PONG,
    MSG_LOCAL_PROTOCOL_SIGNATURE,
    MSG_LOCAL_PROTOCOL_SIGNATURE_DOWN,
    MSG_LOCAL_PROTOCOL_SIGNATURE_UP,
    MSG_NODE_NA,
    MSG_NODETAB,
    MSG_NODETAB_COUNT,
    MSG_NODETAB_GETALL,
    MSG_NODETAB_GETNEXT,
    MSG_PKT_CAPACITY,
    MSG_STRING,
    MSG_STRING_GET,
    MSG_STRING_SET,
    MSG_SYS_DISABLE,
    MSG_SYS_ENABLE,
    MSG_SYS_GET_MAGIC,
    MSG_SYS_GET_P_VERSION,
    MSG_SYS_GET_SW_VERSION,
    MSG_SYS_GET_UNIQUE_ID,
    MSG_SYS_IDENTIFY,
    MSG_SYS_IDENTIFY_STATE,
    MSG_SYS_MAGIC,
    MSG_SYS_P_VERSION,
    MSG_SYS_PING,
    MSG_SYS_PONG,
    MSG_SYS_RESET,
    MSG_SYS_SW_VERSION,
    MSG_SYS_UNIQUE_ID,
    PROTO_VERSION,
    SIGNATURE_TEXT,
    SW_VERSION,
    BidibMessage,
    MessageDecoder,
    SerialPacketDecoder,
    canonical_local,
    encode_iso_string,
    encode_local,
    encode_message,
    find_descriptor_uid,
    generate_uid,
    is_link_type,
    is_signature_type,
    uid_from_hex,
    uid_to_hex,
)
from bidib2wled.config import AppConfig, NetBidibConfig, save_config
from bidib2wled.core import Engine

log = logging.getLogger(__name__)


@dataclass
class PairingRequest:
    peer_uid: str
    prod: str = ""
    user: str = ""
    received_at: float = field(default_factory=time.time)


class NetBidibSession:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        adapter: "NetBidibAdapter",
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.adapter = adapter
        self.decoder = MessageDecoder()
        self.serial_decoder = SerialPacketDecoder()
        self.peer_uid: bytes | None = None
        self.peer_prod = ""
        self.peer_user = ""
        self.peer_role = 0
        self.link_paired = False
        self.logged_on = False
        self.tx_seq = 0
        self.enabled = False
        self.feature_iter = 0
        self.nodetab_sent = False
        self.identify = False
        self._closed = False
        self.last_rx = b""
        self.rx_types: list[int] = []
        self._framing: str | None = None
        self.tx_sig = MSG_LOCAL_PROTOCOL_SIGNATURE_UP
        self.tx_link = MSG_LOCAL_LINK_UP

    @property
    def peer_hex(self) -> str:
        return uid_to_hex(self.peer_uid) if self.peer_uid else ""

    async def run(self) -> None:
        peer = self.writer.get_extra_info("peername")
        log.info("netBiDiB-Verbindung von %s", peer)
        sock = self.writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
        try:
            await self.send_local(MSG_LOCAL_PROTOCOL_SIGNATURE, SIGNATURE_TEXT)
            await self._send_descriptor()
            while not self._closed:
                chunk = await self.reader.read(4096)
                if not chunk:
                    break
                self.last_rx = (self.last_rx + chunk)[-512:]
                if not self.logged_on:
                    log.info("netBiDiB rx %d Byte: %s", len(chunk), chunk[:80].hex())
                for message in self._decode(chunk):
                    self.rx_types.append(message.msg_type)
                    await self._handle(message)
                if not self.peer_uid:
                    uid = find_descriptor_uid(self.last_rx)
                    if uid:
                        log.info("Peer-UID aus Rohdaten: %s", uid_to_hex(uid))
                        self.peer_uid = uid
                        await self._on_peer_identified()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("netBiDiB-Session Fehler")
        finally:
            await self.close()

    def _decode(self, chunk: bytes) -> list[BidibMessage]:
        if self._framing is None and chunk:
            self._framing = "serial" if chunk[0] == 0xFE else "net"
            log.info("netBiDiB-Framing: %s", self._framing)
        if self._framing == "serial":
            return self.serial_decoder.feed(chunk)
        messages = self.decoder.feed(chunk)
        if not messages and chunk and chunk[0] == 0xFE:
            self._framing = "serial"
            log.info("netBiDiB-Framing: serial (Fallback)")
            return self.serial_decoder.feed(chunk)
        return messages

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.logged_on:
            self.logged_on = False
            self.adapter.logged_session = None
        if (
            self.adapter.pending_pairing
            and self.peer_uid
            and self.adapter.pending_pairing.peer_uid == uid_to_hex(self.peer_uid)
        ):
            self.adapter.pending_pairing = None
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass
        self.adapter.sessions.discard(self)
        log.info("netBiDiB-Verbindung geschlossen (%s)", self.peer_hex)

    async def _send_raw(self, data: bytes) -> None:
        self.writer.write(data)
        await self.writer.drain()

    async def send_local(self, msg_type: int, data: bytes = b"") -> None:
        if is_signature_type(msg_type):
            msg_type = self.tx_sig
        elif is_link_type(msg_type):
            msg_type = self.tx_link
        await self._send_raw(encode_local(msg_type, data))

    async def send_up(self, msg_type: int, data: bytes = b"") -> None:
        if not self.logged_on and not (0x70 <= (msg_type & 0x7F) <= 0x7F):
            return
        self.tx_seq = self.tx_seq + 1 if self.tx_seq < 255 else 1
        await self._send_raw(
            encode_message(BidibMessage(msg_type=msg_type, data=data, addr=b"\x00", seq=self.tx_seq))
        )

    async def _send_descriptor(self) -> None:
        uid = self.adapter.uid
        cfg = self.adapter.net_cfg
        await self.send_local(MSG_LOCAL_LINK, bytes([BIDIB_LINK_DESCRIPTOR_UID]) + uid)
        await self.send_local(
            MSG_LOCAL_LINK, bytes([BIDIB_LINK_DESCRIPTOR_P_VERSION, PROTO_VERSION[0], PROTO_VERSION[1]])
        )
        await self.send_local(
            MSG_LOCAL_LINK, bytes([BIDIB_LINK_DESCRIPTOR_PROD_STRING]) + encode_iso_string("BiDiB2WLED")
        )
        await self.send_local(
            MSG_LOCAL_LINK,
            bytes([BIDIB_LINK_DESCRIPTOR_USER_STRING]) + encode_iso_string(cfg.knotenname),
        )
        await self.send_local(MSG_LOCAL_LINK, bytes([BIDIB_LINK_DESCRIPTOR_ROLE, BIDIB_ROLE_NODE]))

    async def _handle(self, message: BidibMessage) -> None:
        if not self.logged_on:
            log.info(
                "netBiDiB Nachricht 0x%02X data=%s",
                message.msg_type,
                message.data[:40].hex() or "-",
            )
        local = canonical_local(message.msg_type)
        if is_signature_type(message.msg_type):
            self.tx_sig = message.msg_type
            if not message.data.startswith(b"BiDiB"):
                log.warning("Ungültige Protocol-Signature, Trennung")
                await self.close()
            return
        if is_link_type(message.msg_type):
            self.tx_link = message.msg_type
            await self._handle_link(message.data)
            return
        if message.msg_type in (MSG_LOCAL_LOGON_ACK,) or local == MSG_LOCAL_LOGON_ACK:
            uid = self.adapter.uid
            if uid in message.data or message.data[1:8] == uid:
                self.logged_on = True
                self.adapter.logged_session = self
                self.tx_seq = 0
                log.info("Logon akzeptiert von %s", self.peer_hex)
            else:
                log.warning("LOGON_ACK UID passt nicht: %s", message.data.hex())
            return
        if message.msg_type in (MSG_LOCAL_LOGON_REJECTED,) or local == MSG_LOCAL_LOGON_REJECTED:
            self.logged_on = False
            if self.adapter.logged_session is self:
                self.adapter.logged_session = None
            await self.send_local(MSG_LOCAL_LOGOFF, self.adapter.uid)
            return
        if local == MSG_LOCAL_PING:
            await self.send_local(MSG_LOCAL_PONG, message.data)
            return

        if not self.logged_on:
            log.debug("Ignoriere Nachricht 0x%02X vor Logon", message.msg_type)
            if message.data[:1] == bytes([BIDIB_LINK_DESCRIPTOR_UID]) and len(message.data) >= 8:
                await self._handle_link(message.data)
            return

        handlers = {
            MSG_SYS_GET_MAGIC: self._on_get_magic,
            MSG_SYS_GET_P_VERSION: self._on_p_version,
            MSG_SYS_GET_UNIQUE_ID: self._on_unique_id,
            MSG_SYS_GET_SW_VERSION: self._on_sw_version,
            MSG_SYS_PING: self._on_ping,
            MSG_SYS_IDENTIFY: self._on_identify,
            MSG_SYS_ENABLE: self._on_enable,
            MSG_SYS_DISABLE: self._on_disable,
            MSG_SYS_RESET: self._on_reset,
            MSG_GET_PKT_CAPACITY: self._on_capacity,
            MSG_NODETAB_GETALL: self._on_nodetab_all,
            MSG_NODETAB_GETNEXT: self._on_nodetab_next,
            MSG_FEATURE_GETALL: self._on_feature_all,
            MSG_FEATURE_GETNEXT: self._on_feature_next,
            MSG_FEATURE_GET: self._on_feature_get,
            MSG_FEATURE_SET: self._on_feature_set,
            MSG_STRING_GET: self._on_string_get,
            MSG_STRING_SET: self._on_string_set,
            MSG_ACCESSORY_SET: self._on_acc_set,
            MSG_ACCESSORY_GET: self._on_acc_get,
            MSG_ACCESSORY_PARA_GET: self._on_acc_para_get,
        }
        handler = handlers.get(message.msg_type)
        if handler:
            await handler(message)
        else:
            log.debug("Unbehandelte BiDiB-Nachricht 0x%02X data=%s", message.msg_type, message.data.hex())

    async def _handle_link(self, data: bytes) -> None:
        if not data:
            return
        opcode = data[0]
        rest = data[1:]
        log.info("netBiDiB LINK 0x%02X von %s (%s)", opcode, self.peer_user or self.peer_prod or "?", self.peer_hex)
        if opcode == BIDIB_LINK_DESCRIPTOR_UID and len(rest) >= 7:
            self.peer_uid = rest[:7]
            await self._on_peer_identified()
            return
        if opcode == BIDIB_LINK_DESCRIPTOR_PROD_STRING and rest:
            self.peer_prod = rest[1 : 1 + rest[0]].decode("latin-1", errors="replace")
            return
        if opcode == BIDIB_LINK_DESCRIPTOR_USER_STRING and rest:
            self.peer_user = rest[1 : 1 + rest[0]].decode("latin-1", errors="replace")
            return
        if opcode == BIDIB_LINK_DESCRIPTOR_ROLE and rest:
            self.peer_role = rest[0]
            return
        if opcode == BIDIB_LINK_STATUS_PAIRED and len(rest) >= 14:
            if self.adapter.pairing_open or (
                self.peer_uid and uid_to_hex(self.peer_uid) in self.adapter.trusted
            ):
                if self.peer_uid:
                    self.adapter.trust(uid_to_hex(self.peer_uid))
                self.link_paired = True
                self.adapter.pending_pairing = None
                self.adapter.pairing_open = False
                await self._try_logon()
            return
        if opcode == BIDIB_LINK_STATUS_UNPAIRED:
            self.link_paired = False
            return
        if opcode == BIDIB_LINK_PAIRING_REQUEST and len(rest) >= 14:
            peer = rest[:7]
            self.peer_uid = self.peer_uid or peer
            self._mark_pending()
            log.info("Pairing-Anfrage von %s (%s)", self.peer_user or self.peer_prod, uid_to_hex(peer))
            if self.adapter.pairing_open:
                await self._accept_peer()
            return

    def _mark_pending(self) -> None:
        if not self.peer_uid:
            return
        self.adapter.pending_pairing = PairingRequest(
            peer_uid=uid_to_hex(self.peer_uid),
            prod=self.peer_prod,
            user=self.peer_user,
        )

    async def _on_peer_identified(self) -> None:
        hex_uid = uid_to_hex(self.peer_uid) if self.peer_uid else ""
        trusted = hex_uid in self.adapter.trusted
        log.info("Peer-UID %s vertraut=%s pairing_open=%s", hex_uid, trusted, self.adapter.pairing_open)
        if trusted:
            await self.send_local(
                MSG_LOCAL_LINK, bytes([BIDIB_LINK_STATUS_PAIRED]) + self.adapter.uid + self.peer_uid
            )
            self.link_paired = True
            await self._try_logon()
            return
        self._mark_pending()
        if self.adapter.pairing_open:
            await self._accept_peer()
            return
        await self.send_local(
            MSG_LOCAL_LINK, bytes([BIDIB_LINK_STATUS_UNPAIRED]) + self.adapter.uid + self.peer_uid
        )

    async def _accept_peer(self) -> None:
        if not self.peer_uid:
            log.warning("Pairing ohne Peer-UID – Host muss verbunden sein")
            return
        hex_uid = uid_to_hex(self.peer_uid)
        self.adapter.trust(hex_uid)
        self.link_paired = True
        await self.send_local(
            MSG_LOCAL_LINK,
            bytes([BIDIB_LINK_PAIRING_REQUEST]) + self.adapter.uid + self.peer_uid,
        )
        await self.send_local(
            MSG_LOCAL_LINK,
            bytes([BIDIB_LINK_STATUS_PAIRED]) + self.adapter.uid + self.peer_uid,
        )
        self.adapter.pending_pairing = None
        self.adapter.pairing_open = False
        await self._try_logon()

    async def reject_pairing(self) -> None:
        if not self.peer_uid:
            return
        await self.send_local(
            MSG_LOCAL_LINK,
            bytes([BIDIB_LINK_STATUS_UNPAIRED]) + self.adapter.uid + self.peer_uid,
        )
        self.adapter.pending_pairing = None

    async def user_pair(self) -> None:
        self.adapter.pairing_open = True
        if not self.peer_uid and self.last_rx:
            uid = find_descriptor_uid(self.last_rx)
            if uid:
                self.peer_uid = uid
        if self.peer_uid:
            await self._accept_peer()
            return
        log.info("Pairing-Modus aktiv, Descriptor erneut senden")
        await self.send_local(MSG_LOCAL_PROTOCOL_SIGNATURE, SIGNATURE_TEXT)
        await self._send_descriptor()

    async def _try_logon(self) -> None:
        if self.logged_on or not self.link_paired:
            return
        if self.adapter.logged_session and self.adapter.logged_session is not self:
            await self.send_local(MSG_LOCAL_LOGOFF, self.adapter.uid)
            return
        await self.send_local(MSG_LOCAL_LOGON, self.adapter.uid)

    async def _on_get_magic(self, _msg: BidibMessage) -> None:
        await self.send_up(MSG_SYS_MAGIC, bytes([BIDIB_SYS_MAGIC & 0xFF, BIDIB_SYS_MAGIC >> 8]))

    async def _on_p_version(self, _msg: BidibMessage) -> None:
        await self.send_up(MSG_SYS_P_VERSION, bytes([PROTO_VERSION[0], PROTO_VERSION[1]]))

    async def _on_unique_id(self, _msg: BidibMessage) -> None:
        await self.send_up(MSG_SYS_UNIQUE_ID, self.adapter.uid)

    async def _on_sw_version(self, _msg: BidibMessage) -> None:
        await self.send_up(MSG_SYS_SW_VERSION, bytes(SW_VERSION))

    async def _on_ping(self, msg: BidibMessage) -> None:
        await self.send_up(MSG_SYS_PONG, msg.data[:1] or b"\x00")

    async def _on_identify(self, msg: BidibMessage) -> None:
        self.identify = bool(msg.data[:1] and msg.data[0])
        await self.send_up(MSG_SYS_IDENTIFY_STATE, bytes([1 if self.identify else 0]))

    async def _on_enable(self, _msg: BidibMessage) -> None:
        self.enabled = True

    async def _on_disable(self, _msg: BidibMessage) -> None:
        self.enabled = False

    async def _on_reset(self, _msg: BidibMessage) -> None:
        self.enabled = False
        self.tx_seq = 0

    async def _on_capacity(self, _msg: BidibMessage) -> None:
        await self.send_up(MSG_PKT_CAPACITY, bytes([64]))

    async def _on_nodetab_all(self, _msg: BidibMessage) -> None:
        self.nodetab_sent = False
        await self.send_up(MSG_NODETAB_COUNT, bytes([1]))

    async def _on_nodetab_next(self, _msg: BidibMessage) -> None:
        if self.nodetab_sent:
            await self.send_up(MSG_NODE_NA, bytes([0]))
            return
        self.nodetab_sent = True
        await self.send_up(MSG_NODETAB, bytes([1, 0]) + self.adapter.uid)

    async def _features(self) -> list[tuple[int, int]]:
        count = max(len(self.adapter.accessory_map()), 1)
        return [
            (FEATURE_ACCESSORY_COUNT, min(count, 127)),
            (FEATURE_ACCESSORY_SURVEILLED, 1),
            (FEATURE_STRING_SIZE, 24),
            (FEATURE_RELEVANT_PID_BITS, 16),
        ]

    async def _on_feature_all(self, _msg: BidibMessage) -> None:
        feats = await self._features()
        self.feature_iter = 0
        await self.send_up(MSG_FEATURE_COUNT, bytes([len(feats)]))

    async def _on_feature_next(self, _msg: BidibMessage) -> None:
        feats = await self._features()
        if self.feature_iter >= len(feats):
            await self.send_up(MSG_FEATURE_NA, bytes([255]))
            return
        num, val = feats[self.feature_iter]
        self.feature_iter += 1
        await self.send_up(MSG_FEATURE, bytes([num, val]))

    async def _on_feature_get(self, msg: BidibMessage) -> None:
        if not msg.data:
            return
        feats = dict(await self._features())
        num = msg.data[0]
        if num in feats:
            await self.send_up(MSG_FEATURE, bytes([num, feats[num]]))
        else:
            await self.send_up(MSG_FEATURE_NA, bytes([num]))

    async def _on_feature_set(self, msg: BidibMessage) -> None:
        await self._on_feature_get(msg)

    async def _on_string_get(self, msg: BidibMessage) -> None:
        if len(msg.data) < 2:
            return
        ns, sid = msg.data[0], msg.data[1]
        text = ""
        if ns == 0 and sid == 0:
            text = "BiDiB2WLED"
        elif ns == 0 and sid == 1:
            text = self.adapter.net_cfg.knotenname
        elif ns == 2:
            mapping = self.adapter.accessory_map()
            text = mapping.get(sid, "")
        payload = bytes([ns, sid]) + encode_iso_string(text)
        await self.send_up(MSG_STRING, payload)

    async def _on_string_set(self, msg: BidibMessage) -> None:
        await self._on_string_get(msg)

    def _acc_total(self, object_id: str) -> int:
        return max(self.adapter.engine.config.aspect_count(object_id), 2)

    async def send_acc_state(
        self,
        anum: int,
        aspect: int,
        *,
        wait: bool,
        wait_time: int = 0,
        notify: bool = False,
        error: int | None = None,
    ) -> None:
        mapping = self.adapter.accessory_map()
        obj = mapping.get(anum)
        total = self._acc_total(obj) if obj else 2
        if error is not None:
            data = bytes([anum, 255, total, BIDIB_ACC_STATE_ERROR | error, 0])
        elif wait:
            data = bytes([anum, aspect, total, BIDIB_ACC_STATE_WAIT, wait_time & 0xFF])
        else:
            data = bytes([anum, aspect, total, BIDIB_ACC_STATE_DONE, 0])
        msg_type = MSG_ACCESSORY_NOTIFY if notify else MSG_ACCESSORY_STATE
        await self.send_up(msg_type, data)

    async def _on_acc_set(self, msg: BidibMessage) -> None:
        if len(msg.data) < 2:
            return
        anum, aspect = msg.data[0], msg.data[1]
        mapping = self.adapter.accessory_map()
        obj = mapping.get(anum)
        if obj is None:
            await self.send_up(
                MSG_ACCESSORY_STATE,
                bytes([255, 255, 0, BIDIB_ACC_STATE_ERROR | BIDIB_ACC_STATE_ERROR_VOID, 0]),
            )
            return
        total = self._acc_total(obj)
        if aspect != 254 and aspect >= total:
            await self.send_acc_state(anum, aspect, wait=False, error=BIDIB_ACC_STATE_ERROR_VOID)
            return
        await self.send_acc_state(anum, aspect, wait=True, wait_time=10)
        asyncio.create_task(self.adapter.apply_accessory(anum, aspect, self))

    async def _on_acc_get(self, msg: BidibMessage) -> None:
        if not msg.data:
            return
        anum = msg.data[0]
        mapping = self.adapter.accessory_map()
        obj = mapping.get(anum)
        if obj is None:
            await self.send_up(
                MSG_ACCESSORY_STATE,
                bytes([255, 255, 0, BIDIB_ACC_STATE_ERROR | BIDIB_ACC_STATE_ERROR_VOID, 0]),
            )
            return
        st = self.adapter.engine.state_of(obj)
        await self.send_acc_state(anum, st.aspect, wait=st.in_progress, wait_time=5)

    async def _on_acc_para_get(self, msg: BidibMessage) -> None:
        if len(msg.data) < 2:
            return
        anum, para = msg.data[0], msg.data[1]
        await self.send_up(MSG_ACCESSORY_PARA, bytes([anum, BIDIB_ACCESSORY_PARA_NOTEXIST, para]))


class NetBidibAdapter:
    def __init__(self, engine: Engine, config_path, save_cb=None) -> None:
        self.engine = engine
        self.config_path = config_path
        self._save_cb = save_cb
        self.net_cfg = NetBidibConfig()
        self.uid = generate_uid()
        self.trusted: set[str] = set()
        self.sessions: set[NetBidibSession] = set()
        self.logged_session: NetBidibSession | None = None
        self.pending_pairing: PairingRequest | None = None
        self.pairing_open = False
        self._server: asyncio.AbstractServer | None = None
        self._client_task: asyncio.Task | None = None
        self.engine.on_status(self._on_engine_status)

    def configure(self, config: AppConfig) -> None:
        self.net_cfg = config.adapter.netbidib
        if self.net_cfg.unique_id:
            try:
                self.uid = uid_from_hex(self.net_cfg.unique_id)
            except ValueError:
                log.warning("Ungültige unique_id in der Konfiguration, generiere neu")
                self.uid = generate_uid()
                self.net_cfg.unique_id = uid_to_hex(self.uid)
        else:
            self.net_cfg.unique_id = uid_to_hex(self.uid)
        self.trusted = {item.lower() for item in self.net_cfg.trusted}

    def accessory_map(self) -> dict[int, str]:
        return self.engine.config.accessory_map()

    def trust(self, uid_hex: str) -> None:
        uid_hex = uid_hex.lower()
        self.trusted.add(uid_hex)
        if uid_hex not in self.net_cfg.trusted:
            self.net_cfg.trusted.append(uid_hex)
            if self._save_cb:
                self._save_cb()

    async def start(self) -> None:
        if not self.net_cfg.aktiv:
            log.info("netBiDiB-Adapter deaktiviert")
            return
        if self.net_cfg.modus == "server":
            self._server = await asyncio.start_server(
                self._on_connect, "0.0.0.0", self.net_cfg.port
            )
            log.info("netBiDiB-Server lauscht auf Port %s", self.net_cfg.port)
        else:
            if not self.net_cfg.host:
                raise ValueError("netBiDiB-Client braucht adapter.netbidib.host")
            self._client_task = asyncio.create_task(self._client_loop())

    async def stop(self) -> None:
        for session in list(self.sessions):
            await session.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._client_task:
            self._client_task.cancel()
            self._client_task = None

    async def restart(self, config: AppConfig) -> None:
        await self.stop()
        self.configure(config)
        await self.start()

    async def _on_connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        session = NetBidibSession(reader, writer, self)
        self.sessions.add(session)
        await session.run()

    async def _client_loop(self) -> None:
        while True:
            try:
                reader, writer = await asyncio.open_connection(self.net_cfg.host, self.net_cfg.port)
                session = NetBidibSession(reader, writer, self)
                self.sessions.add(session)
                await session.run()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("netBiDiB-Client: %s – neuer Versuch in 5s", exc)
            await asyncio.sleep(5)

    async def apply_accessory(self, anum: int, aspect: int, session: NetBidibSession) -> None:
        mapping = self.accessory_map()
        obj = mapping.get(anum)
        if obj is None:
            return
        try:
            await self.engine.switch(obj, aspect, source="bidib")
            await session.send_acc_state(anum, aspect, wait=False)
        except Exception:
            await session.send_acc_state(anum, aspect, wait=False, error=BIDIB_ACC_STATE_ERROR_VOID)

    async def _on_engine_status(self, object_id: str, aspect: int, in_progress: bool) -> None:
        session = self.logged_session
        if session is None or not session.logged_on:
            return
        reverse = {v: k for k, v in self.accessory_map().items()}
        anum = reverse.get(object_id)
        if anum is None:
            return
        await session.send_acc_state(anum, aspect, wait=in_progress, wait_time=5, notify=True)

    async def accept_pairing(self) -> None:
        self.pairing_open = True
        for session in list(self.sessions):
            await session.user_pair()

    async def reject_pairing(self) -> None:
        for session in list(self.sessions):
            await session.reject_pairing()
        self.pending_pairing = None
        self.pairing_open = False
