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
