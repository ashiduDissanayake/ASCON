# Build and run every Verilog testbench in tb/ against the RTL in rtl/.
#
# Usage:
#   make            # run every testbench
#   make pS         # run a single testbench, e.g. ascon_pS_tb
#   make vectors    # regenerate vectors/*.vec from the Python reference model
#   make clean      # remove simulation build products
#
# Icarus Verilog is invoked with -g2012 because rtl/ascon_pC.v declares its
# input ports as `input reg`, which is only accepted under IEEE 1800
# (SystemVerilog) parsing rules in Icarus.

IVERILOG ?= iverilog
VVP      ?= vvp
IFLAGS   := -g2012 -I tb

BUILD := build

RTL_COMMON := rtl/ascon_pC.v rtl/ascon_pS.v rtl/ascon_pL.v rtl/ascon_round_const.v rtl/ascon_round.v rtl/ascon_permutation.v

.PHONY: all clean vectors pC pS pL round permutation controller handshake uart_recovery stub_smoke

all: pC pS pL round permutation controller handshake uart_recovery stub_smoke

vectors:
	python3 model/gen_vectors.py

$(BUILD):
	mkdir -p $(BUILD)

pC: $(BUILD)
	$(IVERILOG) $(IFLAGS) -o $(BUILD)/ascon_pC_tb.out tb/ascon_pC_tb.v rtl/ascon_pC.v rtl/ascon_round_const.v
	$(VVP) $(BUILD)/ascon_pC_tb.out

pS: $(BUILD)
	$(IVERILOG) $(IFLAGS) -o $(BUILD)/ascon_pS_tb.out tb/ascon_pS_tb.v rtl/ascon_pS.v
	$(VVP) $(BUILD)/ascon_pS_tb.out

pL: $(BUILD)
	$(IVERILOG) $(IFLAGS) -o $(BUILD)/ascon_pL_tb.out tb/ascon_pL_tb.v rtl/ascon_pL.v
	$(VVP) $(BUILD)/ascon_pL_tb.out

round: $(BUILD)
	$(IVERILOG) $(IFLAGS) -o $(BUILD)/ascon_round_tb.out tb/ascon_round_tb.v rtl/ascon_round.v rtl/ascon_pC.v rtl/ascon_pS.v rtl/ascon_pL.v rtl/ascon_round_const.v
	$(VVP) $(BUILD)/ascon_round_tb.out

permutation: $(BUILD)
	$(IVERILOG) $(IFLAGS) -o $(BUILD)/ascon_permutation_tb.out tb/ascon_permutation_tb.v $(RTL_COMMON)
	$(VVP) $(BUILD)/ascon_permutation_tb.out

controller: $(BUILD)
	$(IVERILOG) $(IFLAGS) -o $(BUILD)/ascon_controller_tb.out tb/ascon_controller_tb.v rtl/ascon_controller.v rtl/ascon_pad.v $(RTL_COMMON)
	$(VVP) $(BUILD)/ascon_controller_tb.out

handshake: $(BUILD)
	$(IVERILOG) $(IFLAGS) -o $(BUILD)/ascon_controller_handshake_tb.out tb/ascon_controller_handshake_tb.v rtl/ascon_controller.v rtl/ascon_pad.v $(RTL_COMMON)
	$(VVP) $(BUILD)/ascon_controller_handshake_tb.out

uart_recovery: $(BUILD)
	$(IVERILOG) $(IFLAGS) -o $(BUILD)/ascon_uart_recovery_tb.out tb/ascon_uart_recovery_tb.v rtl/ascon_uart_protocol.v
	$(VVP) $(BUILD)/ascon_uart_recovery_tb.out

stub_smoke: $(BUILD)
	$(IVERILOG) $(IFLAGS) -o $(BUILD)/tb_stub_smoke.out tb/tb_stub_smoke.v tb/stub_always_fail.v
	-$(VVP) $(BUILD)/tb_stub_smoke.out

clean:
	rm -rf $(BUILD) dump*.vcd

.PHONY: deadline_vectors fast buffered bounded_uart bounded_uart_nominal deadline formal_deadline
deadline_vectors: $(BUILD)
	python3 model/gen_deadline_vectors.py

fast: deadline_vectors
	$(IVERILOG) $(IFLAGS) -DASCON_DUT=ascon_controller_fast -s ascon_controller_tb -o $(BUILD)/fast.out tb/ascon_controller_tb.v rtl/*.v
	$(VVP) $(BUILD)/fast.out +novcd +vectors=build/fast_cases.vec
	$(IVERILOG) $(IFLAGS) -DASCON_DUT=ascon_controller_fast -s ascon_controller_handshake_tb -o $(BUILD)/fast_handshake.out tb/ascon_controller_handshake_tb.v rtl/*.v
	$(VVP) $(BUILD)/fast_handshake.out

buffered: deadline_vectors
	$(IVERILOG) $(IFLAGS) -s ascon_buffered_tb -o $(BUILD)/buffered.out tb/ascon_buffered_tb.v rtl/*.v
	$(VVP) $(BUILD)/buffered.out

bounded_uart: deadline_vectors
	$(IVERILOG) $(IFLAGS) -s ascon_bounded_uart_tb -o $(BUILD)/bounded_uart.out tb/ascon_bounded_uart_tb.v rtl/*.v
	$(VVP) $(BUILD)/bounded_uart.out

bounded_uart_nominal: deadline_vectors
	$(IVERILOG) $(IFLAGS) -s ascon_bounded_uart_tb -Pascon_bounded_uart_tb.CLKS_PER_BIT=868 -Pascon_bounded_uart_tb.QUICK=1 -o $(BUILD)/bounded_uart_nominal.out tb/ascon_bounded_uart_tb.v rtl/*.v
	$(VVP) $(BUILD)/bounded_uart_nominal.out

deadline: fast buffered bounded_uart
	python3 -m unittest discover -s tests -p 'test_*.py'

formal_deadline:
	bash scripts/prove_deadline.sh
