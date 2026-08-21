#!/usr/bin/env python3
"""Generate line-oriented AEAD and permutation vectors for Verilog simulation."""

from __future__ import annotations

import json
from pathlib import Path

from refmodel import encrypt, permutation


ROOT = Path(__file__).resolve().parents[1]
VECTOR_DIR = ROOT / "vectors"
PROMPT_PATH = ROOT / "NIST-KAT" / "prompt.json"
EXPECTED_PATH = ROOT / "NIST-KAT" / "expectedResults.json"


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

    states = [tuple(range(5)), (0, 0, 0, 0, 0), (0x0123456789ABCDEF,) * 5]
    with (VECTOR_DIR / "submodule_cases.vec").open("w", encoding="ascii") as output:
        for state in states:
            result = permutation(state)
            input_hex = "".join(f"{word:016X}" for word in state)
            output.write(f"{input_hex} {''.join(f'{word:016X}' for word in result)}\n")


if __name__ == "__main__":
    write_vectors()