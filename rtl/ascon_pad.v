// ascon_pad: simple byte-oriented pad helper for Ascon AEAD blocks.
//
// This module is intentionally small and testable in isolation. It models the
// common AEAD padding pattern used in pyascon/ascon.py:
//   pad = data || 0x01 || 00...00
// where the pad byte is inserted at the first empty byte position after the
// valid payload bytes in a rate-sized block.
module ascon_pad (
    input  wire [127:0] data_in,
    input  wire [4:0]  valid_bytes,
    output wire [127:0] padded_out
);

    function automatic [127:0] pad_word;
        input [127:0] data;
        input [4:0] valid;
        integer byte_index;
        reg [127:0] out;
        begin
            out = data;
            if (valid < 16) begin
                byte_index = valid;
                out[(byte_index * 8) +: 8] = 8'h01;
            end
            pad_word = out;
        end
    endfunction

    assign padded_out = pad_word(data_in, valid_bytes);

endmodule
