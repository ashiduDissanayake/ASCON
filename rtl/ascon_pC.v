module ascon_pC (
    input reg [63:0] s2_in,
    input reg [3:0] const_idx,
    output wire [63:0] s2_out
);

    wire [7:0] rc;

    ascon_round_const u_rc (
        .const_idx(const_idx),
        .rc(rc)
    );

    assign s2_out = s2_in ^ {56'b0, rc};

endmodule