# ASCON hardware verification

This repository contains the Python reference model, NIST ACVP vectors, and a file-driven Verilog verification harness.

The local `pyascon/` directory is a required dependency for the Python model. After obtaining it, generate vectors with:

```sh
python3 model/gen_vectors.py
```

Run the official comparable-subset check with:

```sh
python3 NIST-KAT/compare_kat.py
```

Use `python3 NIST-KAT/compare_kat.py --strict` to require zero skipped official encryption vectors.