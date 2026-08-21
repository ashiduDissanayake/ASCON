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

The current `pyascon` API supports byte-oriented Ascon-AEAD128 without ACVP nonce masking. The report therefore compares byte-aligned encryption vectors in the non-masked group and records the remaining official vectors as skipped. In addition, it cross-checks the byte-oriented `NIST-KAT/LWC_AEAD_KAT_128_128.txt` KAT reference, which exercises the full Ascon-AEAD128 byte-range and gives a 100% KAT pass signal for the supported API. If the file is absent, `compare_kat.py` regenerates it into the repo-tracked `NIST-KAT/` directory before running the check. The report includes `checkedVectors`, `skippedVectors`, and `coveragePercent` alongside the more specific ACVP/LWC coverage breakdowns. A normal `PASS` means every supported vector matched; it does not claim full ACVP coverage for nonce-masked or bit-granular cases. `--strict` intentionally fails until nonce masking and non-byte-length processing are implemented.

The local implementation is expected at `pyascon/`, beside this directory. A fresh checkout must include that directory or clone the upstream pyascon implementation there before running the comparator.
