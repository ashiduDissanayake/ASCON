// ascon_keyxor: simple key-injection helper for the Ascon state.
//
// The real AEAD algorithm injects the 128-bit key into the state at fixed word
// positions during initialization/finalization. This helper keeps the logic
// explicit and testable: it XORs the low and high 64-bit key halves into the
// first two state words, which matches the usual post-initialization pattern.
// For finalization the same helper can be reused with a different word mapping.
module ascon_keyxor (
    input  wire [63:0] x0_in,
    input  wire [63:0] x1_in,
    input  wire [63:0] x2_in,
    input  wire [63:0] x3_in,
    input  wire [63:0] x4_in,
    input  wire [127:0] key,
    output wire [63:0] x0_out,
    output wire [63:0] x1_out,
    output wire [63:0] x2_out,
    output wire [63:0] x3_out,
    output wire [63:0] x4_out
);

    assign x0_out = x0_in;
    assign x1_out = x1_in;
    assign x2_out = x2_in;
    assign x3_out = x3_in ^ key[127:64];
    assign x4_out = x4_in ^ key[63:0];

endmodule
