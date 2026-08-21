module stub_always_fail (
    input wire [319:0] state_in,
    output wire [319:0] state_out
);
    assign state_out = 320'b0;
endmodule