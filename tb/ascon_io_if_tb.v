`timescale 1ns/1ps

module ascon_io_if_tb;
    reg        clk;
    reg        rst_n;
    reg [127:0] data_in;
    reg        valid_in;
    reg        last_in;
    reg        ready_in;
    wire       ready_out;
    wire [127:0] data_out;
    wire       valid_out;
    wire       last_out;

    ascon_io_if dut (
        .clk(clk),
        .rst_n(rst_n),
        .data_in(data_in),
        .valid_in(valid_in),
        .last_in(last_in),
        .ready_out(ready_out),
        .data_out(data_out),
        .valid_out(valid_out),
        .ready_in(ready_in),
        .last_out(last_out)
    );

    always #5 clk = ~clk;

    initial begin
        $dumpfile("dump_io_if.vcd");
        $dumpvars(0, ascon_io_if_tb);

        clk = 0;
        rst_n = 0;
        data_in = 128'h11223344556677889900AABBCCDDEEFF;
        valid_in = 0;
        last_in = 0;
        ready_in = 0;

        #12;
        rst_n = 1;
        valid_in = 1;
        last_in = 1;

        #10;
        ready_in = 1;
        #10;

        if ((valid_out === 1'b1) && (data_out === data_in) && (last_out === 1'b1)) begin
            $display("PASS ascon_io_if");
        end else begin
            $display("FAIL ascon_io_if");
            $finish;
        end

        $finish;
    end
endmodule
