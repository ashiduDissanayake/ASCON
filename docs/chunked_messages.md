# Automatic large-message handling in the desktop application

The desktop service splits encryption inputs of **257–8192 bytes** into
sequential AEAD operations containing at most 256 payload bytes each. Inputs
up to 256 bytes retain the existing single-operation result format and nonce
behavior. Empty input remains supported only where the selected firmware allows
it (ASC3/software demo); ASC4 still requires at least one payload byte.

This is a host message layer above the existing FPGA UART ABI. No RTL,
bitstream, buffer size or per-operation execution schedule changes are needed.
It works with ASC3, updated ASC4, and older fixed-48-AD ASC4 because every chunk
uses exactly 48 bytes of cryptographic AD. The onboard UAV host would need this
same message layer; it is currently implemented in the desktop application.

## GUI workflow

1. Enter text or hex, or load a data file, and click **Send & encrypt**. Large
   inputs are split automatically. The GUI shows completed chunk counts.
2. Export the full result JSON. It contains a `message` object with all chunk
   nonces, ciphertexts and tags. It excludes the secret key and plaintext.
3. Click **Load this result for decryption**, or **Copy message JSON** and paste
   it into the multiline decryption input, or **Import encrypted result JSON**
   and enter the matching key, then **Send & decrypt**. The imported
   envelope supplies its own AD, nonce and tags; the separate form fields are
   not used to change those authenticated values.
4. Plaintext appears only after all chunks authenticate. Structural errors,
   authentication failures or transport failures produce no accepted message.

For 1000 bytes the payload lengths are 256, 256, 256 and 232 bytes. The copied
ciphertext hex alone is insufficient for decryption; keep the full JSON.
The decryption selector distinguishes **Ciphertext hex** from **Message / result
JSON**. Pasting JSON selects JSON mode automatically. It accepts the bare message
envelope and the complete exported result wrapper. In JSON mode the separate
nonce, AD, encoding, empty-input and tag controls are disabled: the JSON supplies
the authenticated metadata. The result pane lists each chunk's nonce and tag.
Loading encrypted input clears the previous result until verification completes.

Older single-operation result JSON files can also be imported or pasted. They
populate the raw ciphertext fields, including empty AD/payload flags, while
preserving the key entered by the user. Raw legacy ciphertext above 256 bytes
can still be decrypted by ASC3 (up to 8192 bytes) or the software demo; ASC4
rejects that raw length. Concatenated chunk ciphertext is insufficient because
it has multiple nonces and tags: use the complete message JSON for chunked data.

## Version 1 framing

`basys3-ascon-message-v1` envelopes contain:

- `algorithm`: `Ascon-AEAD128`.
- `base_nonce_hex`: a freshly generated random 128-bit range start per message.
- `associated_data_hex`: the original application AD (0–8192 bytes).
- `plaintext_bytes`: original message length (257–8192).
- `chunks`: canonical ordered list of objects containing `index`, `nonce_hex`,
  `ciphertext_hex` and `tag_hex`. Every tag is 16 bytes. Every payload is 256
  bytes except the final payload, which is exactly the remaining length.

Each nonce is the unsigned big-endian base nonce plus the chunk index. The base
is sampled with Python `secrets` from a range that prevents 128-bit overflow.
Chunked encryption always generates a fresh base, even when the GUI's manual
nonce mode is selected. Random generation provides probabilistic uniqueness
across application restarts; deployments needing managed nonce allocation
should integrate their session/key lifecycle rather than reuse a saved base.

Each chunk's AD is exactly 48 bytes:

| Bytes | Encoding |
|---|---|
| 0–31 | SHA-256 of `b'ASCON-message-v1\0'`, original AD byte length as LE32, original AD, and the 16-byte base nonce, concatenated in that order |
| 32–35 | ASCII `AMC1` |
| 36–39 | Zero-based chunk index, LE32 |
| 40–43 | Total chunk count, LE32 |
| 44–47 | Original plaintext byte length, LE32 |

The hash commits the full original AD and message identity while leaving room
for authenticated ordering and length within the hardware's AD limit. It is a
public framing hash, not a replacement for the AEAD tag. All framing is
validated before UART submission. The receiver rejects missing, duplicate,
reordered and incorrectly sized chunks; tags bind the committed AD and framing.
This layer does not implement session provisioning, replay prevention,
retransmission or UAV radio framing. An entire previously valid envelope may
still be replayed unless a higher layer rejects it.

## Timing and verification

Exports include per-chunk FPGA cycle/time receipts and total FPGA execution
time when the firmware supplies those receipts. Host round-trip time measures
all operations and transfers. The 187-cycle / nominal 1.87-microsecond maximum
remains a **per-operation** bound; it is not a whole-message transfer bound.
The original post-route/board qualification limitations still apply.

Run `python -m unittest discover -s tests -v`. Host tests cover reference
round-trips through the UART parser for ASC3, both ASC4 capability profiles,
lengths 257/512/1000/8192, malformed envelopes, late authentication failures,
AD commitment, fresh nonces, JSON export/import, clipboard/paste round-trips,
metadata control states, multiline editing, legacy imports and headless GUI
verification/failure handlers.
These tests do not constitute physical-board validation.
