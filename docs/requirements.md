# Gateway requirements and timing contract

Current implementation addition: the bounded laboratory UART v4 path supports
48 AD bytes and 1–256 payload bytes with a proved maximum of 187 internal
admission-to-decision cycles. FPGA route/board timing remains open. This does
not complete the future secure gateway or its policy checks. See
[deadline.md](deadline.md) for its exact scope and evidence.

Baseline: `be5456ca02407e47c8aadcd434642779b279d6d8`, reviewed 2026-09-22.
The supplied remaining-implementation plan governs the work order. The proposal
is supporting context. No simulation, board or timing pass is inferred from it.

## Profiles and scope

Use a host flight-controller emulator initially. The application endpoint is
not yet selected. Payload sizes 16, 32, 64, 128 and 256 bytes are exploratory
profiles, not established UAV requirements. Include 0, 1, 15, 17, 31 and 33
bytes in correctness testing. The future command gateway admits 1–256 payload
bytes and exactly 48 AD bytes. Empty payload is valid for core tests only.

The existing UART v3 remains a trusted laboratory interface, with provisional
decryption output. It is not a secure command endpoint. The bounded laboratory
transport supports AD and payload independently up to 8192 bytes.

## Interfaces

Core configuration is sampled on a rising edge with `start && !busy` while
idle. Start while busy is ignored. AD and payload transfer only on
`valid && ready` at a rising edge. Producers hold valid and data until transfer.
A final partial beat occupies the low byte lanes; lengths determine padding.
Zero lengths require no input beat. Outputs hold data, byte count, last and
valid during backpressure. Decryption bytes remain provisional until
`done && auth_ok`. Reset aborts without completion.

## Timing boundaries

| Metric | Start edge | Finish event | Assumptions |
|---|---|---|---|
| Core service | accepted start | done/tag decision | inputs available; output ready |
| Gateway | complete bounded packet admitted | release eligible or rejected | one admitted packet; no queue |
| End to end | host submits command | emulator accepts complete command | includes transport and host scheduling |

100 MHz / 10 ns is the initial clock and implementation target. Two
microseconds equals 200 cycles and is an engineering target for gateway
eligibility, excluding packet loading and command output transfer. UART 115200
8N1 costs 10/115200 seconds per byte, so it cannot support a two-microsecond
end-to-end claim. Internal measurements require preloaded data.

## Bounded workload and recovery

Proposed gateway: one transaction including release, no waiting queue, no
preemption, burst capacity one. Admission is ready/valid. Telemetry and command
admission share this limit; there is no priority guarantee yet. Admit the next
packet only after prior release/rejection completes. For bounded output
completion the emulator accepts each offered beat within 32 clock cycles.

UART: host sends only granted bytes, one operation at a time. A configurable
receive-inactivity timer defaults to 100 ms at 100 MHz. Timeout aborts the core,
clears pending state, and emits error 04. After an error, stop sending, drain
the error record, wait a full timeout interval of silence, then send a header.
Late bytes restart the quiet interval. Physical reset also requires draining
host serial input before starting again.

## Session, nonce and threat assumptions (future gateway contract)

Provision keys and session state through a trusted local interface, separately
from packets. Reset locks command release until a fresh session is provisioned.
The authority must never reuse a session under the same key, including after
reboot. Use a strictly increasing 56-bit sequence per session and direction,
beginning at zero; reject duplicates and lower values. Do not wrap. Commit the
highest accepted sequence only after authentication and all policy checks pass.

Nonce = session LE64 || direction U8 || sequence LE56. The authenticated expiry
is a 64-bit tick deadline in the trusted session clock domain. Accept only if
now <= expiry and expiry-now <= 1,000,000 ticks (10 ms at 100 MHz); no modular
time arithmetic. Synchronization error must be established before deployment.

Threat model: hostile packet injection, modification, replay and delay; trusted
provisioning, clock and local endpoint. Unlimited denial of service, side
channels, physical key extraction and fault injection are outside this claim.

## Completion gates

G1: these provisional contracts exist; endpoint requirements remain open.
G2: correct stream and recovery behavior, run independent and generated
regression, and inspect scripted post-route timing/CDC/DRC before integrating
new security or architecture logic. G3–G6 remain future work until G2 passes.
Owners and reviewers require team assignment; no individuals are inferred.
