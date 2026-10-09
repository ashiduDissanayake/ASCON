# Bounded ASCON execution and hardware signoff

## Status

Implemented and verified in RTL simulation and bounded formal checks. Post-route
100 MHz timing and a Basys 3 board measurement are **not yet verified**. The old
`timing_1.rpx` belongs to an earlier implementation and cannot sign off this RTL.
The new absorption/input-mux path can be longer than the old critical path;
the 100 MHz route must pass before claiming a physical two-microsecond guarantee.

## Exact contract

UART v4 (`ASC4`) admits **exactly 48 AD bytes and 1–256 payload bytes**.
Encryption and decryption use the same schedule. Load the entire input into
the FPGA, then accept `admit_valid && admit_ready`. The finish event is the
first assertion of `response_valid`, containing the final authentication/tag
decision. Loading, waiting for admission, response consumption and output
transfer are outside this interval. There is one transaction slot and no queue.

For payload length M bytes:

```
core cycles = 58 + 8 * floor(M / 16)
admission-to-decision cycles = 59 + 8 * floor(M / 16)
```

The maximum is **187 cycles**, nominally **1.87 us at 100 MHz**. This is a full
AEAD operation including initialization, AD, payload, padding, finalization and
authentication comparison. It is not a per-round or first-output measurement.
At 128 bytes the decision takes 123 cycles; at 256 bytes it takes 187.
Count elapsed rising-edge intervals, not both endpoint edges inclusively.

The buffer feeds all input beats and accepts all output beats internally.
External backpressure during drain cannot stall the admitted operation.
Output is masked to zero until a successful response is acknowledged; a
failed decryption produces no externally valid plaintext. The 199-cycle
watchdog rejects a deadline fault; a watchdog rejection is **not** successful
cryptographic completion. Reset aborts the transaction and clears visible
validity. Loading/draining can wait indefinitely and have separate contracts.

The guarantee assumes no reset/fault during execution, a continuously running
qualified clock, and operation within the part's rated voltage/temperature
limits. Establish actual minimum clock frequency: 187 cycles requires more
than 93.5 MHz to remain strictly below 2 us. Do not infer clock frequency from
the UART baud or a software wall-clock timer. Static timing accounts for path
delay; cycle proofs account for operation length. Both are required.

## Implementation

`ascon_controller_fast` owns one shared `ascon_round`. AD/payload absorption and
final key XOR feed the first round directly; post-init key XOR and final tag
XOR are captured with the last round. The rate is still one round per cycle;
no cryptographic rounds are removed. The bounded instance uses nine-bit length
counters after validating the profile. Generic instances retain 32-bit lengths.

`ascon_buffered` stores three AD beats, up to sixteen input beats and sixteen
output beats. `ascon_uart_buffered_protocol` and `ascon_basys3_bounded_top` connect
it to the real USB-UART pins. The earlier UART v3 top and controller remain
available for the 0–8192-byte laboratory interface.

This is a bounded laboratory AEAD execution endpoint. The proposed session,
replay, expiry and command-policy gateway remains future work; adding those
checks requires a new timing budget and verification.

## Verification commands and observed results

Install Python 3, Icarus Verilog 12 and Yosys 0.33 or compatible versions.
Run from the repository root:

```sh
python3 NIST-KAT/compare_kat.py
make
make deadline
make bounded_uart_nominal
make formal_deadline
```

Observed in this change:

| Check | Result |
|---|---|
| Python reference comparison | 1092 checked, zero mismatches; 117 unsupported ACVP cases skipped |
| Existing functional regression | 234 module/controller vectors; handshake and UART recovery passed |
| Generic fast core | 5980 encryption/decryption vectors; randomized output stalls passed |
| Buffered endpoint | 1792 cases: every length 1–256; encrypt, valid decrypt and five tampering classes |
| Buffered worst case | 187 cycles; loading/output stalls, invalid lengths, resets during load/run/drain checked |
| Accelerated serial-pin integration | 35 reference cases; timing frames, authentication-gated output, timeout/recovery checked |
| Nominal 115200 serial-pin integration | Three maximum-length cases: encrypt, valid decrypt and bad-tag rejection; recovery/reset checked |
| Host transport | Five tests including partial reads, v3 compatibility and malformed/missing timing records |
| Formal core | Actual control cone, all admitted lengths and arbitrary data; exact schedule, <=186 core cycles |
| Formal buffered endpoint | Actual feeder/capture control, all admitted lengths and arbitrary data; exact schedule, <=187 cycles |
| Generic synthesis | Yosys synthesis/check passed; not an FPGA placement/timing result |

`make` also runs the repository's intentionally failing `stub_smoke` harness
demonstration. Its expected failure is unrelated to cryptographic acceptance.
The formal runs cover one transaction from reset through completion; the
buffered harness holds the response and supplies valid load beats. Simulation
covers consecutive packets, loading/output stalls and reset/abort behavior.
Cryptographic correctness is checked against the independent Python reference;
the deadline proof does not assert correctness of the cryptographic outputs.

## Vivado and board completion

Run on the team's Vivado machine:

```sh
vivado -mode batch -source scripts/build_bounded_vivado.tcl
```

On Windows, append `-tclargs C:/path/to/ASCON` if the Desktop path is redirected.
Results are under `build/vivado/ascon_basys3_bounded_top/`. Preserve the metadata,
source hashes, routed checkpoint, bitstream and every report together. The
script checks setup/hold, internal timing coverage, critical CDC and blocking
DRC before writing the bitstream. Review `exceptions.rpt`, `check_timing.rpt`
and `clock_interaction.rpt`, including the intentional asynchronous UART/reset
exceptions. The UART TX pin has a 5 ns propagation budget; LEDs are untimed
visual indicators. The declared 100 ps input jitter budget needs board-source
qualification. Constraint endpoint mismatches fail the build.

Program the **new bounded bitstream**, press btnC, and use the updated desktop
console with 48 AD bytes and 1–256 payload bytes. For a hex example, AD can be
`00 01 ... 2f`; use a fresh nonce for each encryption. The console auto-detects
ASC3/ASC4 and displays FPGA service microseconds separately from host round trip.
The usual five-byte default AD example belongs to v3 and will be rejected by v4.
For an automated board check after programming, install the desktop requirements
and run `python3 tools/check_bounded_board.py --port COM4` (use the real serial
port). It compares board output against the independent reference at five
lengths in both directions, checks the cycle receipt and rejects a changed tag.
It prints JSON to stdout; redirect it to a file to retain the board receipt.
Record the FPGA
cycle count and, ideally, capture `u_buffer.core_start`, `response_valid`,
`elapsed_cycles` and the authentication decision with an ILA. An ILA changes
the implementation, so sign off and retain the report for that exact build too.

If routing fails 100 MHz, inspect the reported path before changing architecture.
There is a 12-cycle budget before the 199-cycle deadline; registered buffer reads
or absorption staging may fit, but require updating the formula and proofs.
Do not mark the hardware deadline complete until route and board evidence exist.
