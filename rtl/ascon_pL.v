// ascon_pL: Ascon linear diffusion layer, NIST SP 800-232.
//
// Applies word-wise Sigma functions to each of the 5 state words:
//   x0 ^= ROTR(x0,19) ^ ROTR(x0,28)
//   x1 ^= ROTR(x1,61) ^ ROTR(x1,39)
//   x2 ^= ROTR(x2, 1) ^ ROTR(x2, 6)
//   x3 ^= ROTR(x3,10) ^ ROTR(x3,17)
//   x4 ^= ROTR(x4, 7) ^ ROTR(x4,41)
//
// Matches model/refmodel.py::permutation's `rotations` table and
// pyascon/ascon.py::ascon_permutation's linear diffusion layer.
module ascon_pL (
    input  wire [63:0] x0_in,
    input  wire [63:0] x1_in,
    input  wire [63:0] x2_in,
    input  wire [63:0] x3_in,
    input  wire [63:0] x4_in,
    output wire [63:0] x0_out,
    output wire [63:0] x1_out,
    output wire [63:0] x2_out,
    output wire [63:0] x3_out,
    output wire [63:0] x4_out
);

    function [63:0] rotr;
        input [63:0] value;
        input integer amount;
        begin
            rotr = (value >> amount) | (value << (64 - amount));
        end
    endfunction

    assign x0_out = x0_in ^ rotr(x0_in, 19) ^ rotr(x0_in, 28);
    assign x1_out = x1_in ^ rotr(x1_in, 61) ^ rotr(x1_in, 39);
    assign x2_out = x2_in ^ rotr(x2_in, 1)  ^ rotr(x2_in, 6);
    assign x3_out = x3_in ^ rotr(x3_in, 10) ^ rotr(x3_in, 17);
    assign x4_out = x4_in ^ rotr(x4_in, 7)  ^ rotr(x4_in, 41);

endmodule
