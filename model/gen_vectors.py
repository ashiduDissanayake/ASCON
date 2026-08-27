#!/usr/bin/env python3
"""Generate line-oriented AEAD and permutation vectors for Verilog simulation."""

from __future__ import annotations

import json
from pathlib import Path

from refmodel import decrypt_raw, encrypt, permutation, permutation_stages


ROOT = Path(__file__).resolve().parents[1]
VECTOR_DIR = ROOT / "vectors"
PROMPT_PATH = ROOT / "NIST-KAT" / "prompt.json"
EXPECTED_PATH = ROOT / "NIST-KAT" / "expectedResults.json"

# Cap on how much AD/PT/CT a single controller_cases.vec record may carry.
# tb/ascon_controller_tb.v sizes its per-vector beat arrays from this same
# constant (as MAX_BEATS), so the two must be kept in sync by hand.
CONTROLLER_MAX_BYTES = 128


def hex_or_underscore(value: bytes) -> str:
    return value.hex().upper() or "_"


def truncate_bits(value: bytes, bit_length: int) -> bytes:
    byte_length, remainder = divmod(bit_length, 8)
    if remainder:
        byte_length += 1
    result = bytearray(value[:byte_length])
    if remainder:
        result[-1] &= (1 << remainder) - 1
    return bytes(result)


def _iter_aead_records(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        if " = " in line:
            label, value = line.split(" = ", 1)
            current[label.strip()] = value.strip()
        elif line.endswith(" ="):
            label = line[:-2].strip()
            current[label] = ""
        else:
            raise ValueError(f"Malformed AEAD vector line: {line!r}")
    if current:
        records.append(current)
    return records


def read_aead_vector(source: str | Path) -> dict[str, bytes] | list[dict[str, bytes]]:
    """Read one or more LWC-style AEAD KAT records.

    The canonical text encoding is a sequence of key-value pairs such as
    ``Key = ...``, ``Nonce = ...``, ``PT = ...``, ``AD = ...``, and ``CT = ...``.
    Empty fields are represented as blank values. A record may optionally include a
    ``Count`` field, which is ignored when parsed.
    """
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8")
    else:
        text = source

    records = []
    for record in _iter_aead_records(text):
        parsed = {}
        for label, value in record.items():
            if label == "Count":
                continue
            parsed[label] = bytes.fromhex(value) if value else b""
        records.append(parsed)

    if len(records) == 1:
        return records[0]
    return records


def official_cases() -> list[tuple[bytes, bytes, bytes, bytes, bytes, bytes, int]]:
    prompt = json.loads(PROMPT_PATH.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    expected_by_id = {
        (group["tgId"], test["tcId"]): test
        for group in expected["testGroups"]
        for test in group["tests"]
    }
    cases = []
    for group in prompt["testGroups"]:
        if group["direction"] != "encrypt" or group["supportsNonceMasking"]:
            continue
        for test in group["tests"]:
            if test["payloadLen"] % 8 or test["adLen"] % 8:
                continue
            result = expected_by_id[(group["tgId"], test["tcId"])]
            cases.append(
                (
                    bytes.fromhex(test["key"]),
                    bytes.fromhex(test["nonce"]),
                    bytes.fromhex(test["ad"]),
                    bytes.fromhex(test["pt"]),
                    bytes.fromhex(result["ct"]),
                    bytes.fromhex(result["tag"]),
                    test["tagLen"],
                )
            )
    return cases


def aead_cases() -> list[tuple[bytes, bytes, bytes, bytes, bytes, bytes, int]]:
    key = bytes(range(16))
    nonce = bytes(range(16))
    cases = [
        (key, nonce, b"", b""),
        (key, nonce, b"associated-data", b""),
        (key, nonce, b"associated-data", bytes(range(16))),
        (key, nonce, b"associated-data", bytes(range(16))[:15] + b"\x00"),
        (key, nonce, bytes(range(32)), bytes(range(52))),
    ]
    results = []
    for case_key, case_nonce, ad, pt in cases:
        ct, tag = encrypt(case_key, case_nonce, ad, pt)
        results.append((case_key, case_nonce, ad, pt, ct, tag, 128))
    results.extend(official_cases())
    return results


def pack_beats(data: bytes) -> list[int]:
    """Split ``data`` into 16-byte, zero-padded blocks packed as 128-bit
    integers using the same stream-order convention ascon_controller.v's
    ad_data/pc_data_in/pc_data_out ports use: bit range [8*i +: 8] holds
    stream byte i, i.e. byte 0 is the *least*-significant byte of the
    packed word. Returns one entry per 16-byte block, and no entries at
    all for empty input (matching the controller, which never expects a
    beat on a stream whose length is 0).
    """
    beats = []
    for offset in range(0, len(data), 16):
        block = data[offset:offset + 16]
        block = block + bytes(16 - len(block))
        beats.append(int.from_bytes(block, "little"))
    return beats


def controller_cases() -> list[dict[str, object]]:
    """Build ascon_controller-level AEAD vectors: full encrypt and decrypt
    round trips plus the negative-security cases from the HDL proposal's
    testing plan (tampered ciphertext, tampered tag, wrong key, wrong
    nonce, modified associated data).

    Each case records what tb/ascon_controller_tb.v needs to drive the DUT
    (direction, key, nonce, AD, the PT-or-CT input stream, and -- for
    decrypt -- the tag to verify against) plus what it should observe back
    (the CT-or-PT output stream, the recomputed tag, and whether auth_ok
    should assert). For the negative cases the expected output stream is
    still the RTL's actual byte-exact output, computed via
    ``refmodel.decrypt_raw`` rather than assumed to be the original
    plaintext -- ascon_controller.v streams pc_data_out unconditionally,
    independent of the later tag comparison, matching the
    "authentication-before-actuation" model in the proposal (an external
    command buffer, not the core itself, is what must discard the bytes
    when auth_ok is 0).
    """
    key = bytes(range(16))
    nonce = bytes(range(16))
    alt_key = bytes(b ^ 0xFF for b in key)
    alt_nonce = bytes(b ^ 0xFF for b in nonce)

    # (AD, PT) pairs chosen to walk every block-boundary path in the
    # controller's FSM: empty streams, AD-only, a single full-rate block,
    # an AD length that is an exact multiple of the 16-byte rate (exercises
    # the synthetic S_AD_EXTRA block), a PT length that is an exact
    # multiple of the rate (exercises S_PC_EXTRA), and a multi-block,
    # non-aligned tail.
    base_messages = [
        (b"", b""),
        (b"associated-data", b""),
        (b"associated-data", bytes(range(16))),
        (bytes(range(16)), bytes(range(10))),
        (bytes(range(32)), bytes(range(32))),
        (bytes(range(32)), bytes(range(52))),
    ]
    for ad, pt in base_messages:
        assert len(ad) <= CONTROLLER_MAX_BYTES and len(pt) <= CONTROLLER_MAX_BYTES

    cases: list[dict[str, object]] = []

    def add_case(direction: int, case_key: bytes, case_nonce: bytes, ad: bytes,
                 pc_in: bytes, tag_in: bytes, expected_pc_out: bytes,
                 expected_tag: bytes, expected_auth_ok: int) -> None:
        cases.append({
            "dir": direction,
            "key": case_key,
            "nonce": case_nonce,
            "ad": ad,
            "pc_in": pc_in,
            "tag_in": tag_in,
            "expected_pc_out": expected_pc_out,
            "expected_tag": expected_tag,
            "expected_auth_ok": expected_auth_ok,
        })

    for ad, pt in base_messages:
        ct, tag = encrypt(key, nonce, ad, pt)
        add_case(0, key, nonce, ad, pt, bytes(16), ct, tag, 1)
        add_case(1, key, nonce, ad, ct, tag, pt, tag, 1)

    # Negative-security cases, all derived from the single-full-block
    # message so every case shares the same easy-to-read baseline.
    ad, pt = base_messages[2]
    ct, tag = encrypt(key, nonce, ad, pt)

    bad_ct = bytes([ct[0] ^ 0x01]) + ct[1:]
    out, recomputed_tag = decrypt_raw(key, nonce, ad, bad_ct)
    add_case(1, key, nonce, ad, bad_ct, tag, out, recomputed_tag,
              1 if recomputed_tag == tag else 0)

    bad_tag = bytes([tag[0] ^ 0x01]) + tag[1:]
    out, recomputed_tag = decrypt_raw(key, nonce, ad, ct)
    add_case(1, key, nonce, ad, ct, bad_tag, out, recomputed_tag,
              1 if recomputed_tag == bad_tag else 0)

    out, recomputed_tag = decrypt_raw(alt_key, nonce, ad, ct)
    add_case(1, alt_key, nonce, ad, ct, tag, out, recomputed_tag,
              1 if recomputed_tag == tag else 0)

    out, recomputed_tag = decrypt_raw(key, alt_nonce, ad, ct)
    add_case(1, key, alt_nonce, ad, ct, tag, out, recomputed_tag,
              1 if recomputed_tag == tag else 0)

    bad_ad = (bytes([ad[0] ^ 0x01]) + ad[1:]) if ad else b"\x01"
    out, recomputed_tag = decrypt_raw(key, nonce, bad_ad, ct)
    add_case(1, key, nonce, bad_ad, ct, tag, out, recomputed_tag,
              1 if recomputed_tag == tag else 0)

    return cases


def write_controller_vectors() -> None:
    """Write vectors/controller_cases.vec, consumed by
    tb/ascon_controller_tb.v. See docs/vector_format.md for the exact
    positional field layout.
    """
    with (VECTOR_DIR / "controller_cases.vec").open("w", encoding="ascii") as output:
        for case in controller_cases():
            ad_beats = pack_beats(case["ad"])
            pc_beats = pack_beats(case["pc_in"])
            expected_beats = pack_beats(case["expected_pc_out"])
            assert len(pc_beats) == len(expected_beats)

            fields = [
                str(case["dir"]),
                case["key"].hex().upper(),
                case["nonce"].hex().upper(),
                str(len(case["ad"])),
                *(f"{beat:032X}" for beat in ad_beats),
                str(len(case["pc_in"])),
                *(f"{beat:032X}" for beat in pc_beats),
                case["tag_in"].hex().upper(),
                *(f"{beat:032X}" for beat in expected_beats),
                case["expected_tag"].hex().upper(),
                str(case["expected_auth_ok"]),
            ]
            output.write(" ".join(fields) + "\n")


def write_vectors() -> None:
    VECTOR_DIR.mkdir(exist_ok=True)
    with (VECTOR_DIR / "aead_cases.vec").open("w", encoding="ascii") as output:
        for key, nonce, ad, pt, expected_ct, expected_tag, tag_length in aead_cases():
            actual_ct, actual_tag = encrypt(key, nonce, ad, pt)
            result = "PASS" if actual_ct == expected_ct and truncate_bits(actual_tag, tag_length) == truncate_bits(expected_tag, tag_length) else "FAIL"
            output.write(
                " ".join(
                    (
                        key.hex().upper(),
                        nonce.hex().upper(),
                        hex_or_underscore(ad),
                        hex_or_underscore(pt),
                        hex_or_underscore(expected_ct),
                        expected_tag.hex().upper(),
                        result,
                    )
                )
                + "\n"
            )

    write_controller_vectors()

    states = [
        tuple(range(5)),
        (0, 0, 0, 0, 0),
        (0x0123456789ABCDEF,) * 5,
        (0xFFFFFFFFFFFFFFFF,) * 5,
        (0x8000000000000001, 0x0000000000000000, 0xDEADBEEFCAFEBABE, 0x0102030405060708, 0x1122334455667788),
    ]

    def words_to_hex(words: Iterable[int]) -> str:
        return "".join(f"{word:016X}" for word in words)

    with (VECTOR_DIR / "submodule_cases.vec").open("w", encoding="ascii") as output:
        for state in states:
            result = permutation(state)
            output.write(f"{words_to_hex(state)} {words_to_hex(result)}\n")

    # Per-layer vectors: exercise ascon_pS and ascon_pL in isolation across
    # every round of a full 12-round permutation for each seed state, and
    # ascon_round (pC + pS + pL together, with its const_idx input) the same
    # way. This lets tb/ascon_pS_tb.v, tb/ascon_pL_tb.v, and
    # tb/ascon_round_tb.v cross-check each RTL submodule against the exact
    # intermediate state the Python model computes, not just the end-to-end
    # 12-round result.
    with (VECTOR_DIR / "pS_cases.vec").open("w", encoding="ascii") as ps_out, \
         (VECTOR_DIR / "pL_cases.vec").open("w", encoding="ascii") as pl_out, \
         (VECTOR_DIR / "round_cases.vec").open("w", encoding="ascii") as round_out:
        for state in states:
            round_input = tuple(word & 0xFFFFFFFFFFFFFFFF for word in state)
            for stage in permutation_stages(state):
                ps_out.write(f"{words_to_hex(stage['pC'])} {words_to_hex(stage['pS'])}\n")
                pl_out.write(f"{words_to_hex(stage['pS'])} {words_to_hex(stage['pL'])}\n")
                round_out.write(
                    f"{words_to_hex(round_input)} {stage['const_idx']:X} {words_to_hex(stage['pL'])}\n"
                )
                round_input = stage["pL"]


if __name__ == "__main__":
    write_vectors()