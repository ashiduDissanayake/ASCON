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

IVERILOG := iverilog
VVP      := vvp
IFLAGS   := -g2012 -I tb

BUILD := build

RTL_COMMON := rtl/ascon_pC.v rtl/ascon_pS.v rtl/ascon_pL.v rtl/ascon_round_const.v rtl/ascon_round.v rtl/ascon_permutation.v

.PHONY: all clean vectors pC pS pL round permutation controller stub_smoke

all: pC pS pL round permutation controller stub_smoke

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

stub_smoke: $(BUILD)
	$(IVERILOG) $(IFLAGS) -o $(BUILD)/tb_stub_smoke.out tb/tb_stub_smoke.v tb/stub_always_fail.v
	-$(VVP) $(BUILD)/tb_stub_smoke.out

clean:
	rm -rf $(BUILD) dump*.vcd
