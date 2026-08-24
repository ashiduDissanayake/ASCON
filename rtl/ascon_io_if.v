// ascon_io_if: tiny, protocol-agnostic handshaking boundary.
//
// This is intentionally not the final AEAD controller. It is just the minimal
// word-parallel interface boundary to keep the state-owner logic independent of
// the eventual bus protocol. The usual next step is to wrap this in an AXI-Stream
// or a custom ready/valid adapter without changing the internal Ascon core.
module ascon_io_if (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [127:0] data_in,
    input  wire        valid_in,
    input  wire        last_in,
    output wire        ready_out,
    output reg  [127:0] data_out,
    output reg         valid_out,
    input  wire        ready_in,
    output reg         last_out
);

    reg [127:0] hold_reg;
    reg         hold_valid;
    reg         hold_last;

    assign ready_out = !hold_valid;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            hold_reg   <= 128'b0;
            hold_valid <= 1'b0;
            hold_last  <= 1'b0;
            data_out   <= 128'b0;
            valid_out  <= 1'b0;
            last_out   <= 1'b0;
        end else begin
            if (valid_in && !hold_valid) begin
                hold_reg   <= data_in;
                hold_valid <= 1'b1;
                hold_last  <= last_in;
            end

            if (hold_valid && ready_in) begin
                data_out   <= hold_reg;
                valid_out  <= 1'b1;
                last_out   <= hold_last;
                hold_valid <= 1'b0;
            end else begin
                valid_out  <= 1'b0;
                last_out   <= 1'b0;
            end
        end
    end
endmodule
