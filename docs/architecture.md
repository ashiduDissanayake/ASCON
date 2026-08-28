# Architecture

How this repo gets from "NIST's specification" to "verified Verilog", end to end.

## 1. Ground truth: NIST ACVP + pyascon

`NIST-KAT/` holds the official NIST ACVP inputs/outputs (`prompt.json`,
`expectedResults.json`, `registration.json`) for Ascon-AEAD128.
`pyascon/` is a vendored copy of the reference Python implementation --
it's tracked directly in the repo (not a submodule) so a fresh clone is
reproducible with no extra setup.

`NIST-KAT/compare_kat.py` cross-checks `pyascon` against the official ACVP
vectors, and separately against the byte-oriented `LWC_AEAD_KAT_128_128.txt`
KAT file (which it regenerates if missing). This is the check that
`pyascon` itself is a faithful implementation before anything else in the
repo trusts it. See `NIST-KAT/README.md` for exact usage and what
`--strict` means.

## 2. Reference model: `model/`

`model/refmodel.py` is a thin wrapper around `pyascon` that exposes
`encrypt`, `decrypt_raw`, `permutation`, and `permutation_stages` --
the last one records the state after every pC/pS/pL sub-layer of every
round, which is what makes per-layer unit testing of the RTL possible.

`model/gen_vectors.py` drives `refmodel.py` to write every `vectors/*.vec`
file used by the testbenches (see below). Run it with:

```sh
python3 model/gen_vectors.py
```

## 3. Vectors: `vectors/`

Plain text, whitespace-separated, one test case per line -- generated,
not hand-written. Full field layouts are in [`vectors.md`](vectors.md).
There's one file per thing being tested: the full permutation, each
sub-layer (pS/pL/pC via the round-constant index), and the full-AEAD
controller (including negative-security cases like tampered ciphertext).

## 4. RTL: `rtl/`

A bottom-up build of the permutation, reused by an AEAD controller FSM:

- `ascon_round_const.v`, `ascon_pC.v`, `ascon_pS.v`, `ascon_pL.v` -- the
  three per-round layers plus the constant table
- `ascon_round.v` -- one round, composed as `pC -> pS -> pL`
- `ascon_permutation.v` -- the iterative datapath: one `ascon_round`
  instance reused every cycle, driven by a round counter and a
  `start`/`done` handshake, for `ROUNDS` cycles
- `ascon_pad.v` -- small helper reused by the controller
  for block padding
- `ascon_controller.v` -- the top-level AEAD FSM: two `ascon_permutation`
  instances (12 rounds for init/finalization, 8 for intermediate
  AD/PT/CT permutes) plus pad, implementing the full
  Ascon-AEAD128 encrypt/decrypt+verify flow
- `ascon_io_if.v` -- a standalone ready/valid skid buffer, kept as a
  building block for a future bus adapter; `ascon_controller` doesn't
  use it internally

## 5. Testbenches: `tb/` + `Makefile`

Each RTL module has a matching file-driven testbench that reads the
corresponding `vectors/*.vec` file and self-checks against it --
no waveform inspection required to know pass/fail. `tb_stub_smoke.v` /
`stub_always_fail.v` are a minimal, intentionally-failing example of the
harness pattern itself, unrelated to Ascon.

```sh
make            # build + run every testbench (Icarus Verilog)
make pS         # run a single testbench, e.g. the substitution layer
make controller # run just the full-AEAD controller testbench
make vectors    # regenerate vectors/*.vec from the Python reference model
make clean      # remove simulation build products
```

For a Vivado-based flow instead of Icarus, add `rtl/` as design sources
and `tb/` as simulation sources, and copy `vectors/` into Vivado's
simulation sandbox directory (`<project>.sim/sim_1/behav/xsim/`) since
Vivado runs simulations from there rather than the repo root.
