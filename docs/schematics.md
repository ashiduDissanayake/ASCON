# Schematics & simulation gallery

Synthesized schematics (from the `tools/build_skin.py` + netlistsvg flow,
exported to PDF) and Icarus/waveform-viewer simulation screenshots for
every RTL module, generated while verifying against `vectors/*.vec`
(see [`vectors.md`](vectors.md)). These are reference snapshots checked
in for browsing -- regenerate the schematics locally with the `tools/`
scripts rather than treating these as the source of truth for the design.

`ascon_io_if.v` has neither: it's an unused building block for a future
bus adapter (see [`architecture.md`](architecture.md)), not part of the
verified AEAD datapath.

## Round-constant lookup

[`ascon_round_const_schematic.pdf`](assets/schematics/ascon_round_const_schematic.pdf)

## Per-round layers

| Module | Schematic | Simulation |
|---|---|---|
| `ascon_pC` (constant addition) | [PDF](assets/schematics/ascon_pC_schematic.pdf) | ![ascon_pC testbench](assets/simulations/ascon_pC_tb.png) |
| `ascon_pS` (S-box substitution) | [PDF](assets/schematics/ascon_pS_schematic.pdf) | ![ascon_pS testbench](assets/simulations/ascon_pS_tb.png) |
| `ascon_pL` (linear diffusion) | [PDF](assets/schematics/ascon_pL_schematic.pdf) | ![ascon_pL testbench](assets/simulations/ascon_pl_tb.png) |
| `ascon_round` (pC + pS + pL) | [PDF](assets/schematics/ascon_round_schematic.pdf) | ![ascon_round testbench](assets/simulations/ascon_round_tb.png) |

## Permutation core

[`ascon_permutation_schematic.pdf`](assets/schematics/ascon_permutation_schematic.pdf)

![ascon_permutation testbench](assets/simulations/ascon_permutation_tb.png)

## Controller helpers

| Module | Schematic | Simulation |
|---|---|---|
| `ascon_pad` (block padding) | [PDF](assets/schematics/ascon_pad_schematic.pdf) | ![ascon_pad testbench](assets/simulations/ascon_pad_tb.png) |

## Full AEAD controller

[`controller_schematic.pdf`](assets/schematics/controller_schematic.pdf)

Encrypt/decrypt+verify walkthroughs:

![ascon_controller testbench, part 1](assets/simulations/ascon_controller_tb_1.png)
![ascon_controller testbench, part 2](assets/simulations/ascon_controller_tb_2.png)

A second, single-instance controller configuration was also exercised:

![ascon_single_controller testbench](assets/simulations/ascon_single_controller_tb.png)
