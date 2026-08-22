# Vector format

The repository uses a line-oriented AEAD vector format for the LWC-compatible KAT files stored under `pyascon/` and for any generated text vectors consumed by the verification flow.

Each vector is stored as a sequence of key/value pairs. The canonical fields are:

- `Key` = 128-bit key in hexadecimal
- `Nonce` = 128-bit nonce in hexadecimal
- `PT` = plaintext in hexadecimal; empty for a zero-length message
- `AD` = associated data in hexadecimal; empty for zero-length associated data
- `CT` = ciphertext + authentication tag in hexadecimal

A vector may also include an optional `Count` field. The parser ignores it when validating the data because the format is used for stable reference vectors rather than for a numerical index.

Example:

```text
Key = 000102030405060708090A0B0C0D0E0F
Nonce = 000102030405060708090A0B0C0D0E0F
PT = 
AD = 00010203
CT = 6F0A0F8A7F3D... 
```

Important details:

- Fields are separated by a single ` = ` delimiter.
- Empty values are represented by a blank string on the right-hand side.
- Each vector is terminated by a blank line.
- The ciphertext (`CT`) is the full output from the AEAD operation, so the parser can validate both the ciphertext and tag together without any additional metadata.

The repository still keeps the ACVP JSON vectors for the official NIST samples, but the local line-based LWC format is the canonical byte-oriented reference because it exercises the full byte-length KAT range that `pyascon` supports without nonce masking or bit-granular lengths.

## Permutation submodule vectors

`model/gen_vectors.py` also emits four whitespace-separated, one-vector-per-line files consumed directly by the Verilog testbenches in `tb/`. Each 320-bit state is packed as five concatenated 64-bit hex words, most-significant word first (`x0 x1 x2 x3 x4`), matching `ascon_permutation`'s `state_in`/`state_out` bus layout.

- `vectors/submodule_cases.vec`: `<state_in> <state_out>` — full 12-round permutation. Consumed by `tb/ascon_permutation_tb.v` (and by `tb/tb_stub_smoke.v` against the intentionally-failing placeholder `stub_always_fail`).
- `vectors/pS_cases.vec`: `<state after pC> <state after pS>` — one line per round, across every round of several full-permutation traces. Consumed by `tb/ascon_pS_tb.v`.
- `vectors/pL_cases.vec`: `<state after pS> <state after pL>` — one line per round. Consumed by `tb/ascon_pL_tb.v`.
- `vectors/round_cases.vec`: `<state before round> <const_idx hex digit> <state after round>` — one line per round, including the round-constant table index consumed by `ascon_pC`. Consumed by `tb/ascon_round_tb.v`.

All four files are derived from `model/refmodel.py::permutation_stages`, which records the pC/pS/pL intermediate state at every round of the same bit-sliced permutation used by `permutation()` (itself cross-checked against `pyascon.ascon_permutation`). Regenerate all vector files, including these, with:

```sh
python3 model/gen_vectors.py
```
