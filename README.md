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
- `ascon_permutation.v` — the full, parameterized (`ROUNDS`, default 12) permutation. This is an iterative, clocked datapath: a single `ascon_round` instance is reused every cycle, driven by a 320-bit state register, a round counter, and a `start`/`done` handshake. Pulse `start` for one cycle with `state_in` held, wait `ROUNDS` cycles for `done` to pulse, then read `state_out`. This is the area-efficient hardware shape rather than a fully spatially-unrolled combinational block.
- `ascon_keyxor.v` — small helper that XORs a 128-bit key into two state words; reused for both the post-initialization and finalization key injections.
- `ascon_pad.v` — inserts the Ascon `0x01` pad byte at a given byte position in a 128-bit block. Used by `ascon_controller` (see below) for AD/PT/CT block padding.
- `ascon_io_if.v` — a standalone one-slot ready/valid skid buffer/register-slice. It's a building block for a future bus adapter (e.g. AXI-Stream) wrapping `ascon_controller`'s native ports, not something `ascon_controller` uses internally -- the controller's own `ad_*`/`pc_*` ports are already a correctly-handshaked ready/valid interface in their own right.
- `ascon_controller.v` — the top-level AEAD FSM: drives two `ascon_permutation` instances (`ROUNDS=12` for init/finalization, `ROUNDS=8` for intermediate AD/PT/CT permutes), `ascon_keyxor`, and `ascon_pad`, and implements the full Ascon-AEAD128 encrypt/decrypt+verify flow -- key/nonce load, associated-data absorption, plaintext/ciphertext processing (including every block-boundary edge case: empty streams, exact-rate-multiple lengths, multi-block tails), and finalization/tag comparison. See the header comment in the file for the exact byte-ordering and interface conventions.

Each RTL module has a matching file-driven testbench under `tb/`, validated against vectors generated straight from `model/refmodel.py` (see `docs/vector_format.md` for the vector layout):

- `ascon_pC_tb.v`, `ascon_pS_tb.v`, `ascon_pL_tb.v` — per-layer unit tests
- `ascon_round_tb.v` — validates the pC+pS+pL composition against per-round reference traces
- `ascon_permutation_tb.v` — validates the full 12-round permutation end to end
- `ascon_controller_tb.v` — full-AEAD-level test: drives `ascon_controller` through complete `start`..`done` encrypt/decrypt operations against `vectors/controller_cases.vec`, checking the output byte stream, computed tag, and (for decrypt) `auth_ok` on every vector, including the negative-security cases (tampered ciphertext/tag, wrong key/nonce, modified AD) from the proposal's testing plan
- `tb_stub_smoke.v` / `stub_always_fail.v` — a placeholder module and smoke test kept as a minimal example of the file-driven harness; it is expected to fail, since the stub always outputs zero

Run the whole suite with [Icarus Verilog](http://iverilog.icarus.com/) via the provided `Makefile`:

```sh
make            # build and run every testbench
make pS         # run a single testbench, e.g. the substitution-layer one
make controller # run just the full-AEAD controller testbench
make vectors    # regenerate vectors/*.vec from the Python reference model
make clean      # remove simulation build products
```