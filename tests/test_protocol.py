from bidib2wled.adapters import (
    BIDIB_LINK_DESCRIPTOR_UID,
    MSG_LOCAL_LINK_DOWN,
    MSG_SYS_GET_MAGIC,
    MessageDecoder,
    SerialPacketDecoder,
    encode_local,
    encode_message,
    encode_signature,
    find_descriptor_uid,
    generate_uid,
    uid_from_hex,
    uid_to_hex,
    BidibMessage,
)


def test_roundtrip_message():
    raw = encode_message(BidibMessage(msg_type=MSG_SYS_GET_MAGIC, data=b"", seq=3))
    messages = MessageDecoder().feed(raw)
    assert len(messages) == 1
    assert messages[0].msg_type == MSG_SYS_GET_MAGIC
    assert messages[0].seq == 3
    assert messages[0].addr == b"\x00"


def test_signature_starts_with_bidib():
    raw = encode_signature()
    messages = MessageDecoder().feed(raw)
    assert messages[0].data.startswith(b"BiDiB")


def test_split_stream():
    decoder = MessageDecoder()
    a = encode_message(BidibMessage(msg_type=1, seq=1))
    b = encode_message(BidibMessage(msg_type=2, seq=2, data=b"\x01\x02"))
    out = decoder.feed(a[:2] + a[2:] + b)
    assert [m.msg_type for m in out] == [1, 2]
    assert out[1].data == b"\x01\x02"


def test_serial_frame():
    inner = encode_local(0x7E, b"BiDiB2WLED") + b"\x00"
    escaped = bytearray()
    for byte in inner:
        if byte in (0xFE, 0xFD):
            escaped.append(0xFD)
            escaped.append(byte ^ 0x20)
        else:
            escaped.append(byte)
    messages = SerialPacketDecoder().feed(b"\xfe" + bytes(escaped) + b"\xfe")
    assert len(messages) == 1
    assert messages[0].data.startswith(b"BiDiB")


def test_find_descriptor_uid():
    uid = bytes([0xC0, 0, 0x0D, 1, 2, 3, 4])
    msg = encode_local(MSG_LOCAL_LINK_DOWN, bytes([BIDIB_LINK_DESCRIPTOR_UID]) + uid)
    assert find_descriptor_uid(msg) == uid


def test_rocrail_link_uses_type_ff():
    raw = bytes.fromhex(
        "080000fe4269446942"
        "0b0000ffff00934b1f730046"
        "0c0000ff0007526f637261696c"
        "160000ff011128632920522e4a2e20566572736c756973"
        "060000ff800800"
    )
    messages = MessageDecoder().feed(raw)
    assert [m.msg_type for m in messages] == [0xFE, 0xFF, 0xFF, 0xFF, 0xFF]
    assert messages[1].data[0] == BIDIB_LINK_DESCRIPTOR_UID
    assert messages[1].data[1:8].hex() == "00934b1f730046"
    assert messages[2].data[2:].decode("latin-1") == "Rocrail"
    assert find_descriptor_uid(raw).hex() == "00934b1f730046"


def test_uid_hex():
    uid = generate_uid(serial=0x1234)
    assert uid[0] == 0x04
    assert uid[2] == 0x00
    assert uid_from_hex(uid_to_hex(uid)) == uid
