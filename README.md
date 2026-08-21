# ASCON hardware verification

This repository contains the Python reference model, NIST ACVP vectors, and a file-driven Verilog verification harness.

The local `pyascon/` directory is a required dependency for the Python model. After obtaining it, generate vectors with:

```sh
python3 model/gen_vectors.py
```

Run the KAT cross-check against both the official ACVP subset and the representative byte-oriented LWC AEAD vectors with:

```sh
python3 NIST-KAT/compare_kat.py
```

This reports the ACVP subset coverage and the full LWC KAT coverage together. Use `python3 NIST-KAT/compare_kat.py --strict` to require zero skipped official encryption vectors.

The line-based KAT format used by the Python model is documented in `docs/vector_format.md`.