#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/formal
# 190 steps cover reset, admission, the worst 186-cycle operation and done.
# The built-in SAT engine needs no external SMT solver.
yosys -Q -p 'read_verilog -formal rtl/ascon_controller_fast.v rtl/ascon_round.v rtl/ascon_round_const.v rtl/ascon_pC.v rtl/ascon_pS.v rtl/ascon_pL.v formal/ascon_deadline.v; prep -top ascon_deadline -flatten; async2sync; opt_clean; sat -seq 190 -prove-asserts -set-assumes -verify -timeout 60' | tee build/formal/deadline.log
yosys -Q -p 'read_verilog -formal rtl/ascon_buffered.v rtl/ascon_controller_fast.v rtl/ascon_round.v rtl/ascon_round_const.v rtl/ascon_pC.v rtl/ascon_pS.v rtl/ascon_pL.v formal/ascon_buffered_deadline.v; prep -top ascon_buffered_deadline -flatten; async2sync; opt_clean; sat -seq 220 -prove-asserts -set-assumes -verify -timeout 60' | tee build/formal/buffered_deadline.log
