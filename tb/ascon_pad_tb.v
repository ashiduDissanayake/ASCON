`timescale 1ns/1ps

module ascon_pad_tb;
    reg  [127:0] data_in;
    reg  [4:0]   valid_bytes;
    reg  [127:0] expected;
    wire [127:0] padded_out;

    integer i;

    ascon_pad dut (
        .data_in(data_in),
        .valid_bytes(valid_bytes),
        .padded_out(padded_out)
    );

    initial begin
        $dumpfile("dump_pad.vcd");
        $dumpvars(0, ascon_pad_tb);

        for (i = 0; i < 5; i = i + 1) begin
            case (i)
                0: begin
                    data_in = 128'h00000000000000000000000000000000;
                    valid_bytes = 5'd0;
                end
                1: begin
                    data_in = 128'h0123456789ABCDEF0123456789ABCDEF;
                    valid_bytes = 5'd8;
                end
                2: begin
                    data_in = 128'h0123456789ABCDEF0123456789ABCDEF;
                    valid_bytes = 5'd15;
                end
                3: begin
                    data_in = 128'hFEDCBA9876543210FEDCBA9876543210;
                    valid_bytes = 5'd1;
                end
                default: begin
                    data_in = 128'hFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF;
                    valid_bytes = 5'd16;
                end
            endcase

            #1;
            expected = data_in;
            if (valid_bytes < 16) begin
                expected[(valid_bytes * 8) +: 8] = 8'h01;
            end

            if (padded_out === expected) begin
                $display("PASS valid_bytes=%0d padded=%h", valid_bytes, padded_out);
            end else begin
                $display("FAIL valid_bytes=%0d data=%h expected=%h actual=%h",
                         valid_bytes, data_in, expected, padded_out);
                $finish;
            end
        end

        $finish;
    end
endmodule
