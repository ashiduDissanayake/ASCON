# Packet and interface format

## Existing laboratory UART v3

All integers use little endian. A request header is exactly 58 bytes:

| Offset | Bytes | Field |
|---|---:|---|
| 0 | 1 | A5 marker |
| 1 | 1 | 11 encrypt, 12 decrypt |
| 2 | 4 | AD byte length, 0–8192 |
| 6 | 4 | payload byte length, 0–8192 |
| 10 | 16 | laboratory key |
| 26 | 16 | nonce |
| 42 | 16 | expected tag for decrypt; zeros for encrypt |

Do not send AD or payload until requested. Each response is 19 bytes:
`5A type count payload[16]`. Types: 01 capability hello, 10 request AD,
11 request input payload, 12 ciphertext, 14 provisional plaintext, 13 final
tag, and 7F error. Grants and data counts are 1–16. Unused lanes are zero.
Hello payload is ASCII ASC3, maximum length LE32, provisional-output flag 01,
then seven zeros. Error count is: 01 unsupported command, 02 excessive length,
03 authentication failure, 04 receive timeout. Error payload is zero.

Transport bytes are in natural order. Core key/nonce/tag packing is two
little-endian 64-bit words with word zero in bits 127:64. Stream beats place
byte i at bits 8*i +: 8. UART has no transaction IDs; stop-and-wait plus the
abort/reset quiet recovery interval is mandatory.

## Proposed secure packet v1 (not yet a board interface)

Exactly 48 bytes of associated data, followed by 1–256 ciphertext bytes, then
a 16-byte tag. Maximum packet size is 320 bytes. The key is never in a packet.

| AD offset | Bytes | Field |
|---|---:|---|
| 0 | 1 | version = 1 |
| 1 | 1 | type: 1 command, 2 telemetry |
| 2 | 1 | direction: 0 ground-to-UAV, 1 UAV-to-ground |
| 3 | 1 | priority: 0 (only supported value) |
| 4 | 4 | sender ID LE32 |
| 8 | 4 | destination ID LE32 |
| 12 | 8 | session ID LE64 |
| 20 | 7 | sequence LE56 |
| 27 | 1 | reserved = 0 |
| 28 | 2 | payload length LE16 |
| 30 | 2 | reserved = 0 |
| 32 | 8 | expiry tick LE64 |
| 40 | 8 | reserved = 0 |

Authenticate all 48 bytes. Validate version, zero reserved fields, identities,
role/type/direction, session, length and expiry before release. Derive the nonce
from session/direction/sequence as specified in requirements.md. Proposed
profile and freshness constants must be revisited with the chosen endpoint.
