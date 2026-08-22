`ifdef TB_COMMON_IN_MODULE
integer pass_count;
integer fail_count;
integer vector_count;

task automatic init_scoreboard;
begin
    pass_count = 0;
    fail_count = 0;
    vector_count = 0;
end
endtask

task automatic read_state_vector;
    input integer vector_file;
    output reg [319:0] state_in;
    output reg [319:0] state_expected;
    output integer read_count;
begin
    read_count = $fscanf(vector_file, "%h %h\n", state_in, state_expected);
end
endtask

task automatic score_state;
    input integer vector_number;
    input [319:0] state_actual;
    input [319:0] state_expected;
begin
    vector_count = vector_count + 1;
    if (state_actual === state_expected) begin
        pass_count = pass_count + 1;
        $display("PASS vector %0d", vector_number);
    end else begin
        fail_count = fail_count + 1;
        $display("FAIL vector %0d", vector_number);
        $display("  expected = %080h", state_expected);
        $display("  actual   = %080h", state_actual);
        $display("  diff     = %080h", state_actual ^ state_expected);
    end
end
endtask

task automatic report_summary;
begin
    $display("SUMMARY vectors=%0d pass=%0d fail=%0d", vector_count, pass_count, fail_count);
    if (fail_count != 0) begin
        $display("verification failed");
        $finish;
    end
end
endtask

`endif