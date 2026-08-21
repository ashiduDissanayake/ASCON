`timescale 1ns/1ps

module tb_stub_smoke;
    reg [319:0] state_in;
    reg [319:0] state_expected;
    wire [319:0] state_out;
    integer vector_file;
    integer read_count;
    integer vector_number;

    `include "tb_common.vh"

    stub_always_fail dut (
        .state_in(state_in),
        .state_out(state_out)
    );

    initial begin
        init_scoreboard();
        vector_file = $fopen("vectors/submodule_cases.vec", "r");
        if (vector_file == 0)
            $fatal(1, "could not open vectors/submodule_cases.vec");

        vector_number = 1;
        while (!$feof(vector_file)) begin
            read_state_vector(vector_file, state_in, state_expected, read_count);
            if (read_count == 2) begin
                #1;
                score_state(vector_number, state_out, state_expected);
                vector_number = vector_number + 1;
            end
        end

        $fclose(vector_file);
        report_summary();
        $finish;
    end
endmodule