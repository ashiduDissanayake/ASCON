# ASCON hardware verification

A from-scratch Verilog implementation of **Ascon-AEAD128** (NIST SP 800-232),
verified against a Python reference model and the official NIST ACVP vectors.

The project has three layers, each checked against the one below it:

```
NIST ACVP vectors  --check-->  pyascon (reference impl)
                                     |
                                     v
                          model/refmodel.py + gen_vectors.py
                                     |
                                     v  (generates vectors/*.vec)
                              rtl/*.v  <--check-->  tb/*.v  (Icarus Verilog)
```

See [`docs/architecture.md`](docs/architecture.md) for how the pieces fit
together, [`docs/vectors.md`](docs/vectors.md) for the test-vector file
formats, and [`docs/schematics.md`](docs/schematics.md) for a synthesized
schematic and simulation-waveform gallery of every module.

## Quick start

```sh
# 1. Cross-check the Python reference model against NIST's own vectors
python3 NIST-KAT/compare_kat.py

# 2. Generate the Verilog testbench vectors from that same reference model
python3 model/gen_vectors.py

# 3. Build and run every RTL testbench with Icarus Verilog
make            # all testbenches
make controller # just the full-AEAD controller testbench
make handshake  # ready/valid stress and output-backpressure checks
make clean      # remove simulation build products
```

The provisional gateway contract is in [`docs/requirements.md`](docs/requirements.md)
and [`docs/packet_format.md`](docs/packet_format.md). Build the Basys 3 image and
post-route reports with `vivado -mode batch -source scripts/build_vivado.tcl`.
Vivado 2018.1 on Windows may require the repository path as a Tcl argument; see
the comment at the top of `scripts/build_vivado.tcl`.

## Repository layout

| Path | Contents |
|---|---|
| `pyascon/` | Vendored reference Ascon implementation (upstream, used as ground truth) |
| `NIST-KAT/` | Official NIST ACVP vectors + `compare_kat.py` cross-check |
| `model/` | `refmodel.py` (thin wrapper around `pyascon`) and `gen_vectors.py` (emits `vectors/*.vec`) |
| `vectors/` | Generated `.vec` files consumed by the testbenches (not hand-written) |
| `rtl/` | The Verilog design: permutation core, controller FSM, and helper modules |
| `tb/` | One file-driven testbench per RTL module |
| `docs/` | Architecture, vector-format, and schematic/simulation documentation |
| `tools/` | `build_skin.py` / `vsc_hdl_tasks.py` -- regenerate schematics into a local, gitignored `build/` |

Requires [Icarus Verilog](http://iverilog.icarus.com/) (`iverilog`/`vvp`) and Python 3.

## Desktop large messages

The desktop console automatically splits 257–8192-byte encryption inputs into
authenticated operations of at most 256 bytes each. Export/import the full JSON
to decrypt and reassemble the message; every chunk has its own nonce and tag.
Plaintext is shown only after all chunks verify. Inputs up to 256 bytes retain
the existing single-operation behavior. No FPGA bitstream change is needed.
See [the message format and GUI workflow](docs/chunked_messages.md).

```sh
python -m unittest discover -s tests -v
```

## Buffered execution at the two-microsecond target

The optional UART v4 top, `ascon_basys3_bounded_top`, buffers 0–48 AD bytes
and 1–256 payload bytes before admission. Its measured worst RTL latency is
187 cycles (nominally 1.87 us at 100 MHz), including the authentication decision.
It withholds plaintext until authentication succeeds. Post-route timing and
board qualification remain required; the earlier timing screenshot does not
sign off this new design. See [the contract, verification and board steps](docs/deadline.md).

```sh
make deadline
make bounded_uart_nominal
make formal_deadline
vivado -mode batch -source scripts/build_bounded_vivado.tcl
```
