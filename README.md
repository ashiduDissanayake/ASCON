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

## RTL and Verilog verification

`rtl/` contains a from-scratch Verilog implementation of the Ascon permutation, built up from the standard three layers plus a top-level composition:

- `ascon_round_const.v` — 16-entry round-constant lookup table
- `ascon_pC.v` — constant-addition layer (XORs the round constant into word `x2`)
- `ascon_pS.v` — bitsliced 5-bit S-box substitution layer
- `ascon_pL.v` — word-wise linear diffusion layer
- `ascon_round.v` — one full round, composed as `ascon_pC` -> `ascon_pS` -> `ascon_pL`
- `ascon_permutation.v` — the full, parameterized (`ROUNDS`, default 12) permutation, built by unrolling `ascon_round` over a 320-bit `state_in`/`state_out` bus

Each RTL module has a matching file-driven testbench under `tb/`, validated against vectors generated straight from `model/refmodel.py` (see `docs/vector_format.md` for the vector layout):

- `ascon_pC_tb.v`, `ascon_pS_tb.v`, `ascon_pL_tb.v` — per-layer unit tests
- `ascon_round_tb.v` — validates the pC+pS+pL composition against per-round reference traces
- `ascon_permutation_tb.v` — validates the full 12-round permutation end to end
- `tb_stub_smoke.v` / `stub_always_fail.v` — a placeholder module and smoke test kept as a minimal example of the file-driven harness; it is expected to fail, since the stub always outputs zero

Run the whole suite with [Icarus Verilog](http://iverilog.icarus.com/) via the provided `Makefile`:

```sh
make            # build and run every testbench
make pS         # run a single testbench, e.g. the substitution-layer one
make vectors    # regenerate vectors/*.vec from the Python reference model
make clean      # remove simulation build products
```