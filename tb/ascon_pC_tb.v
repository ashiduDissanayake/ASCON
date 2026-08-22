`timescale 1ns/1ps

module ascon_pC_tb;
    // 1. Declare signals
    reg  [63:0] s2_in;
    reg  [3:0]  const_idx;
    wire [63:0] s2_out;
    wire [7:0]  rc_expected;
    reg  [63:0] expected_s2_out;
    
    integer i; // We need an integer for our loop

    // 2. Bring in generic testing tools
`ifndef SYNTHESIS
    `define TB_COMMON_IN_MODULE
    `include "tb_common.vh"
    `undef TB_COMMON_IN_MODULE
`endif

    // 3. Instantiate the module we are testing
    ascon_pC dut (
        .s2_in(s2_in),
        .const_idx(const_idx),
        .s2_out(s2_out)
    );

    // Reference round constant generator for expected-value calculation
    ascon_round_const ref_rc (
        .const_idx(const_idx),
        .rc(rc_expected)
    );

    // 4. Run the test
`ifndef SYNTHESIS
    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(0, ascon_pC_tb);

        init_scoreboard(); // Start tracking passes/fails
        
        // --- TESTING LOOP GOES HERE ---
        for (i = 0; i < 16; i = i + 1) begin
            const_idx = i[3:0];

            // Case 1: all-0 input
            s2_in = 64'h0000000000000000;
            #1;
            expected_s2_out = s2_in ^ {56'b0, rc_expected};
            vector_count = vector_count + 1;
            if (s2_out === expected_s2_out) begin
                pass_count = pass_count + 1;
                $display("PASS vector %0d const_idx=%0d s2_in=0x%016h s2_out=0x%016h",
                         vector_count, const_idx, s2_in, s2_out);
            end else begin
                fail_count = fail_count + 1;
                $display("FAIL vector %0d const_idx=%0d s2_in=0x%016h",
                         vector_count, const_idx, s2_in);
                $display("  expected = %016h", expected_s2_out);
                $display("  actual   = %016h", s2_out);
                $display("  diff     = %016h", s2_out ^ expected_s2_out);
            end

            // Case 2: all-1 input
            s2_in = 64'hffffffffffffffff;
            #1;
            expected_s2_out = s2_in ^ {56'b0, rc_expected};
            vector_count = vector_count + 1;
            if (s2_out === expected_s2_out) begin
                pass_count = pass_count + 1;
                $display("PASS vector %0d const_idx=%0d s2_in=0x%016h s2_out=0x%016h",
                vector_count, const_idx, s2_in, s2_out);
            end else begin
                fail_count = fail_count + 1;
                $display("FAIL vector %0d const_idx=%0d s2_in=0x%016h",
                         vector_count, const_idx, s2_in);
                $display("  expected = %016h", expected_s2_out);
                $display("  actual   = %016h", s2_out);
                $display("  diff     = %016h", s2_out ^ expected_s2_out);
            end
        end
        
        report_summary();  // Print the final results
        $finish;           // Stop the simulation
    end
`endif
endmodule