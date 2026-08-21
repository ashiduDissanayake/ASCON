# NIST ACVP comparison

These files are from the official NIST ACVP Server directory:

- `prompt.json`: official encryption and decryption inputs
- `expectedResults.json`: official expected outputs
- `registration.json`: algorithm and vector registration metadata

Run the comparison from any directory:

```sh
python3 NIST-KAT/compare_kat.py
```

Use `--strict` when a complete official encryption comparison is required:

```sh
python3 NIST-KAT/compare_kat.py --strict
```

The comparator writes `comparison_results.json` in this directory and returns a nonzero exit code when a supported vector differs.

The current `pyascon` API supports byte-oriented Ascon-AEAD128 without ACVP nonce masking. The report therefore compares byte-aligned encryption vectors in the non-masked group and records the remaining official vectors as skipped. It includes `checkedVectors`, `skippedVectors`, and `coveragePercent`. A normal `PASS` means every comparable vector matched; it does not claim full official coverage. `--strict` intentionally fails until nonce masking and non-byte-length processing are implemented.

The local implementation is expected at `pyascon/`, beside this directory. A fresh checkout must include that directory or clone the upstream pyascon implementation there before running the comparator.
