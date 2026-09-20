`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 09/20/2026 05:59:39 PM
// Design Name: 
// Module Name: ascon_basys3_top
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 

// Basys3 top-level wrapper for the existing Ascon-AEAD128 controller.
// USB -> FT2232HQ -> UART -> this module -> ASCON -> UART -> USB.
module ascon_basys3_top #(
    parameter integer CLK_FREQ_HZ = 100_000_000,
    parameter integer BAUD_RATE = 115200
) (
    input  wire CLK100MHZ,
    input  wire btnC,
    input  wire RsRx,
    output wire RsTx,
    output wire [3:0] led
);

    // Asynchronous assertion, synchronous release. Press btnC after programming.
    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_sync;
    always @(posedge CLK100MHZ or posedge btnC) begin
        if (btnC) reset_sync <= 2'b00;
        else reset_sync <= {reset_sync[0], 1'b1};
    end
    wire rst_n = reset_sync[1];

    wire [7:0] rx_data;
    wire       rx_valid;
    wire       rx_busy;

    wire [7:0] tx_data;
    wire       tx_valid;
    wire       tx_busy;

    uart_rx #(
        .CLK_FREQ_HZ(CLK_FREQ_HZ),
        .BAUD_RATE(BAUD_RATE)
    ) u_uart_rx (
        .clk       (CLK100MHZ),
        .rst_n     (rst_n),
        .rx        (RsRx),
        .data_out  (rx_data),
        .data_valid(rx_valid),
        .busy      (rx_busy)
    );

    uart_tx #(
        .CLK_FREQ_HZ(CLK_FREQ_HZ),
        .BAUD_RATE(BAUD_RATE)
    ) u_uart_tx (
        .clk       (CLK100MHZ),
        .rst_n     (rst_n),
        .data_in   (tx_data),
        .data_valid(tx_valid),
        .tx        (RsTx),
        .busy      (tx_busy)
    );

    wire         ascon_start;
    wire         ascon_decrypt;
    wire [127:0] ascon_key;
    wire [127:0] ascon_nonce;
    wire [31:0]  ascon_ad_len;
    wire [31:0]  ascon_pc_len;
    wire [127:0] ascon_tag_in;
    wire         ascon_busy;
    wire         ascon_done;
    wire         ascon_auth_ok;
    wire [127:0] ascon_tag_out;
    wire         ascon_ad_valid;
    wire [127:0] ascon_ad_data;
    wire         ascon_ad_ready;
    wire         ascon_pc_valid;
    wire [127:0] ascon_pc_data;
    wire         ascon_pc_ready;
    wire         ascon_pc_valid_out;
    wire [127:0] ascon_pc_data_out;
    wire [4:0]   ascon_pc_bytes_out;
    wire         ascon_pc_last_out;
    wire         ascon_pc_ready_in;

    ascon_uart_protocol u_protocol (
        .clk                (CLK100MHZ),
        .rst_n              (rst_n),
        .rx_data            (rx_data),
        .rx_valid           (rx_valid),
        .tx_data            (tx_data),
        .tx_valid           (tx_valid),
        .tx_busy            (tx_busy),
        .ascon_start        (ascon_start),
        .ascon_decrypt      (ascon_decrypt),
        .ascon_key          (ascon_key),
        .ascon_nonce        (ascon_nonce),
        .ascon_ad_len       (ascon_ad_len),
        .ascon_pc_len       (ascon_pc_len),
        .ascon_tag_in       (ascon_tag_in),
        .ascon_busy         (ascon_busy),
        .ascon_done         (ascon_done),
        .ascon_auth_ok      (ascon_auth_ok),
        .ascon_tag_out      (ascon_tag_out),
        .ascon_ad_valid     (ascon_ad_valid),
        .ascon_ad_data      (ascon_ad_data),
        .ascon_ad_ready     (ascon_ad_ready),
        .ascon_pc_valid     (ascon_pc_valid),
        .ascon_pc_data      (ascon_pc_data),
        .ascon_pc_ready     (ascon_pc_ready),
        .ascon_pc_valid_out (ascon_pc_valid_out),
        .ascon_pc_data_out  (ascon_pc_data_out),
        .ascon_pc_bytes_out (ascon_pc_bytes_out),
        .ascon_pc_last_out  (ascon_pc_last_out),
        .ascon_pc_ready_in  (ascon_pc_ready_in)
    );

    ascon_controller u_ascon (
        .clk          (CLK100MHZ),
        .rst_n        (rst_n),
        .start        (ascon_start),
        .decrypt      (ascon_decrypt),
        .key          (ascon_key),
        .nonce        (ascon_nonce),
        .ad_len       (ascon_ad_len),
        .pc_len       (ascon_pc_len),
        .tag_in       (ascon_tag_in),
        .busy         (ascon_busy),
        .done         (ascon_done),
        .auth_ok      (ascon_auth_ok),
        .tag_out      (ascon_tag_out),
        .ad_ready     (ascon_ad_ready),
        .ad_valid     (ascon_ad_valid),
        .ad_data      (ascon_ad_data),
        .pc_ready     (ascon_pc_ready),
        .pc_valid     (ascon_pc_valid),
        .pc_data_in   (ascon_pc_data),
        .pc_valid_out (ascon_pc_valid_out),
        .pc_ready_in  (ascon_pc_ready_in),
        .pc_data_out  (ascon_pc_data_out),
        .pc_bytes_out (ascon_pc_bytes_out),
        .pc_last_out  (ascon_pc_last_out)
    );

    // Simple debug indicators.
    assign led[0] = rx_busy;
    assign led[1] = tx_busy;
    assign led[2] = ascon_busy;
    assign led[3] = ascon_done;

endmodule
