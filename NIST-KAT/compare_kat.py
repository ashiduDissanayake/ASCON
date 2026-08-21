#!/usr/bin/env python3
"""Compare pyascon against the official ACVP Ascon-AEAD128 sample vectors."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PYASCON = ROOT.parent / "pyascon"
sys.path.insert(0, str(PYASCON))

import ascon  # noqa: E402


PROMPT_PATH = ROOT / "prompt.json"
EXPECTED_PATH = ROOT / "expectedResults.json"
REPORT_PATH = ROOT / "comparison_results.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def index_tests(document: dict[str, Any], direction: str | None = None) -> dict[tuple[int, int], dict[str, Any]]:
    indexed: dict[tuple[int, int], dict[str, Any]] = {}
    for group in document.get("testGroups", []):
        if direction is not None and group.get("direction") != direction:
            continue
        group_id = group["tgId"]
        for test in group["tests"]:
            key = (group_id, test["tcId"])
            if key in indexed:
                raise ValueError(f"duplicate test identifier: tgId={key[0]}, tcId={key[1]}")
            indexed[key] = test
    return indexed


def truncate_bits(value: bytes, bit_length: int) -> bytes:
    byte_length, remainder = divmod(bit_length, 8)
    if remainder:
        byte_length += 1
    truncated = bytearray(value[:byte_length])
    if remainder:
        truncated[-1] &= (1 << remainder) - 1
    return bytes(truncated)


def compare() -> dict[str, Any]:
    prompt = load_json(PROMPT_PATH)
    expected = load_json(EXPECTED_PATH)
    all_prompt_tests = index_tests(prompt)
    prompt_tests = index_tests(prompt, direction="encrypt")
    expected_tests = index_tests(expected)
    prompt_groups = {
        group["tgId"]: group
        for group in prompt.get("testGroups", [])
    }

    mismatches: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    checked = 0
    for identifier, inputs in prompt_tests.items():
        group = prompt_groups[identifier[0]]
        if group.get("supportsNonceMasking"):
            skipped.append(
                {
                    "tgId": identifier[0],
                    "tcId": identifier[1],
                    "reason": "pyascon does not expose the ACVP nonce-masking operation",
                }
            )
            continue
        if inputs["payloadLen"] % 8 or inputs["adLen"] % 8:
            skipped.append(
                {
                    "tgId": identifier[0],
                    "tcId": identifier[1],
                    "reason": "pyascon accepts byte lengths; this ACVP vector uses a non-byte length",
                }
            )
            continue
        if identifier not in expected_tests:
            mismatches.append({"tgId": identifier[0], "tcId": identifier[1], "error": "missing expected result"})
            continue

        result = expected_tests[identifier]
        key = bytes.fromhex(inputs["key"])
        nonce = bytes.fromhex(inputs["nonce"])
        plaintext = truncate_bits(bytes.fromhex(inputs["pt"]), inputs["payloadLen"])
        associated_data = truncate_bits(bytes.fromhex(inputs["ad"]), inputs["adLen"])
        generated = ascon.ascon_encrypt(
            key,
            nonce,
            associated_data,
            plaintext,
            "Ascon-AEAD128",
        )
        tag_length_bits = inputs["tagLen"]
        generated_ct = truncate_bits(generated[:-16], inputs["payloadLen"])
        generated_tag = truncate_bits(generated[-16:], tag_length_bits)
        expected_ct = truncate_bits(bytes.fromhex(result["ct"]), inputs["payloadLen"])
        expected_tag = truncate_bits(bytes.fromhex(result["tag"]), tag_length_bits)
        checked += 1

        if generated_ct != expected_ct or generated_tag != expected_tag:
            mismatches.append(
                {
                    "tgId": identifier[0],
                    "tcId": identifier[1],
                    "differences": {
                        "ct": {"expected": result["ct"], "actual": generated_ct.hex().upper()}
                        if generated_ct != expected_ct
                        else None,
                        "tag": {"expected": result["tag"], "actual": generated_tag.hex().upper()}
                        if generated_tag != expected_tag
                        else None,
                    },
                }
            )

    report = {
        "algorithm": "Ascon-AEAD128",
        "source": "NIST ACVP Server Ascon-AEAD128-SP800-232",
        "promptVectors": len(all_prompt_tests),
        "encryptVectors": len(prompt_tests),
        "skippedDecryptVectors": len(all_prompt_tests) - len(prompt_tests),
        "expectedVectors": len(expected_tests),
        "checkedVectors": checked,
        "skippedVectors": len(skipped),
        "mismatchCount": len(mismatches),
        "result": "PASS" if not mismatches else "FAIL",
        "mismatches": mismatches,
        "skipped": skipped,
    }
    with REPORT_PATH.open("w", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    return report


if __name__ == "__main__":
    report = compare()
    print(
        f"{report['result']}: checked {report['checkedVectors']} vectors; "
        f"{report['mismatchCount']} mismatches; report={REPORT_PATH.name}"
    )
    raise SystemExit(0 if report["result"] == "PASS" else 1)