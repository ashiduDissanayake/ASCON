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
make clean      # remove simulation build products
```

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
