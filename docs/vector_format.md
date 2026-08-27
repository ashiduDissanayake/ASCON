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

## Controller (full AEAD) vectors

`vectors/controller_cases.vec`, consumed by `tb/ascon_controller_tb.v`, drives `ascon_controller` end to end -- `start` through `done` -- rather than just the permutation core. It is whitespace-separated and positional (no field labels), one record per line, with this field order:

```text
dir key nonce
ad_len ad_beat[0] ad_beat[1] ...
pc_len pc_beat[0] pc_beat[1] ...
tag_in
exp_beat[0] exp_beat[1] ...
exp_tag exp_auth_ok
```

- `dir`: `0` = encrypt, `1` = decrypt+verify.
- `key`, `nonce`, `tag_in`, `exp_tag`: 128-bit hex, same word-first-in-high-bits convention as `ascon_controller`'s own `key`/`nonce`/`tag_in`/`tag_out` ports.
- `ad_len`, `pc_len`: decimal byte counts (`pc_len` excludes the 16-byte tag). `pc_in` is the plaintext for `dir=0` or the ciphertext for `dir=1`.
- `ad_beat[i]` / `pc_beat[i]`: `ceil(len/16)` beats each, 128-bit hex, zero-padded to a full 16-byte block. Packed stream-order (bit `[8*i +: 8]` = stream byte `i`), matching `ad_data`/`pc_data_in`/`pc_data_out`'s own convention -- so a beat can be read directly into a 128-bit reg with a plain `%h`. A length of 0 contributes zero beats.
- `exp_beat[i]`: the expected output stream (ciphertext for `dir=0`, plaintext for `dir=1`), same count and packing as `pc_beat[i]`.
- `exp_auth_ok`: `0` or `1`, meaningful only when `dir=1`.

For negative-security cases (tampered ciphertext/tag, wrong key/nonce, modified AD) the expected output stream and tag are still the RTL's actual byte-exact result -- computed via `refmodel.decrypt_raw`, not assumed to equal the original plaintext -- since `ascon_controller` streams `pc_data_out` and computes `tag_out` unconditionally, independent of the later `auth_ok` check. See `model/gen_vectors.py::controller_cases` for how each case is built, and the proposal's §3.5/§6.4 for the authentication-before-actuation rationale these cases exercise.

