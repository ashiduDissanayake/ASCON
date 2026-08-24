`timescale 1ns/1ps

module ascon_keyxor_tb;
    reg [63:0] x0_in, x1_in, x2_in, x3_in, x4_in;
    reg [127:0] key;
    wire [63:0] x0_out, x1_out, x2_out, x3_out, x4_out;

    ascon_keyxor dut (
        .x0_in(x0_in),
        .x1_in(x1_in),
        .x2_in(x2_in),
        .x3_in(x3_in),
        .x4_in(x4_in),
        .key(key),
        .x0_out(x0_out),
        .x1_out(x1_out),
        .x2_out(x2_out),
        .x3_out(x3_out),
        .x4_out(x4_out)
    );

    initial begin
        $dumpfile("dump_keyxor.vcd");
        $dumpvars(0, ascon_keyxor_tb);

        x0_in = 64'h0123456789ABCDEF;
        x1_in = 64'h1111111111111111;
        x2_in = 64'h2222222222222222;
        x3_in = 64'h3333333333333333;
        x4_in = 64'h4444444444444444;
        key   = 128'h89ABCDEF0123456789ABCDEF01234567;

        #1;

        if ((x0_out === (x0_in ^ key[63:0])) &&
            (x1_out === (x1_in ^ key[127:64])) &&
            (x2_out === x2_in) &&
            (x3_out === x3_in) &&
            (x4_out === x4_in)) begin
            $display("PASS ascon_keyxor");
        end else begin
            $display("FAIL ascon_keyxor");
            $display("  expected x0=%h x1=%h", (x0_in ^ key[63:0]), (x1_in ^ key[127:64]));
            $display("  actual   x0=%h x1=%h", x0_out, x1_out);
            $finish;
        end

        $finish;
    end
endmodule
