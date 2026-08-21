#!/usr/bin/env python3
"""Pure-Python NIST SP 800-232 Ascon-AEAD128 reference-model wrapper."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable


PYASCON = Path(__file__).resolve().parents[1] / "pyascon"
if str(PYASCON) not in sys.path:
    sys.path.insert(0, str(PYASCON))

import ascon  # noqa: E402


MASK64 = 0xFFFFFFFFFFFFFFFF


def _validate(key: bytes, nonce: bytes) -> None:
    if len(key) != 16:
        raise ValueError("Ascon-AEAD128 keys must be 16 bytes")
    if len(nonce) != 16:
        raise ValueError("Ascon-AEAD128 nonces must be 16 bytes")


def _rotate_right(value: int, amount: int) -> int:
    return ((value >> amount) | (value << (64 - amount))) & MASK64


def _state_text(state: list[int]) -> str:
    return " ".join(f"S{i}={word:016X}" for i, word in enumerate(state))


def permutation(state: Iterable[int], rounds: int = 12, trace: bool = False) -> tuple[int, ...]:
    """Apply Ascon's permutation and optionally print pC, pS, and pL states."""
    words = [word & MASK64 for word in state]
    if len(words) != 5:
        raise ValueError("state must contain five 64-bit words")
    if not 0 <= rounds <= 12:
        raise ValueError("rounds must be between 0 and 12")

    for round_number in range(12 - rounds, 12):
        words[2] ^= 0xF0 - round_number * 0x10 + round_number
        if trace:
            print(f"r={round_number:02d} pC {_state_text(words)}")

        words[0] ^= words[4]
        words[4] ^= words[3]
        words[2] ^= words[1]
        temporary = [(words[i] ^ MASK64) & words[(i + 1) % 5] for i in range(5)]
        for index in range(5):
            words[index] ^= temporary[(index + 1) % 5]
        words[1] ^= words[0]
        words[0] ^= words[4]
        words[3] ^= words[2]
        words[2] ^= MASK64
        if trace:
            print(f"r={round_number:02d} pS {_state_text(words)}")

        rotations = ((19, 28), (61, 39), (1, 6), (10, 17), (7, 41))
        for index, (first, second) in enumerate(rotations):
            words[index] ^= _rotate_right(words[index], first) ^ _rotate_right(words[index], second)
            words[index] &= MASK64
        if trace:
            print(f"r={round_number:02d} pL {_state_text(words)}")
    return tuple(words)


def encrypt(key: bytes, nonce: bytes, ad: bytes, pt: bytes, trace: bool = False) -> tuple[bytes, bytes]:
    """Encrypt and return ``(ciphertext, 16-byte authentication tag)``."""
    _validate(key, nonce)
    if trace:
        iv = bytes([1, 0, 0x8C, 0x80, 0, 0x10, 0, 0])
        initial_state = [int.from_bytes((iv + key + nonce)[offset:offset + 8], "little") for offset in range(0, 40, 8)]
        print("trace input " + _state_text(initial_state))
        permutation(initial_state, rounds=12, trace=True)
    output = ascon.ascon_encrypt(key, nonce, ad, pt, "Ascon-AEAD128")
    return output[:-16], output[-16:]


def decrypt(key: bytes, nonce: bytes, ad: bytes, ct: bytes, tag: bytes) -> bytes | None:
    """Verify and decrypt an Ascon-AEAD128 ciphertext."""
    _validate(key, nonce)
    if len(tag) != 16:
        raise ValueError("Ascon-AEAD128 tags must be 16 bytes")
    return ascon.ascon_decrypt(key, nonce, ad, ct + tag, "Ascon-AEAD128")


if __name__ == "__main__":
    encrypt(bytes(16), bytes(16), b"", b"", trace=True)