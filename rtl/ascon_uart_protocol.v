`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 09/20/2026 05:59:16 PM
// Design Name: 
// Module Name: ascon_uart_protocol
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



// Fixed request: A5 01 AD_LEN PT_LEN KEY[16] NONCE[16] AD[16] PT[16].
// Fixed response: 5A STATUS CT[16] TAG[16]. STATUS=00 success, 01 bad
// command, 02 invalid length. Unused CT bytes and error payloads are zero.
// All external fields use natural byte order; only the core bus is repacked.
// One outstanding transaction. Always send all 68 bytes, then read 34 bytes.
// A truncated frame requires btnC reset (no packet timeout in this version).
module ascon_uart_protocol (
    input  wire         clk,
    input  wire         rst_n,

    input  wire [7:0]   rx_data,
    input  wire         rx_valid,

    output reg  [7:0]   tx_data,
    output reg          tx_valid,
    input  wire         tx_busy,

    output reg          ascon_start,
    output reg          ascon_decrypt,
    output reg  [127:0] ascon_key,
    output reg  [127:0] ascon_nonce,
    output reg  [31:0]  ascon_ad_len,
    output reg  [31:0]  ascon_pc_len,
    output reg  [127:0] ascon_tag_in,

    input  wire         ascon_busy,
    input  wire         ascon_done,
    input  wire         ascon_auth_ok,
    input  wire [127:0] ascon_tag_out,

    output reg          ascon_ad_valid,
    output reg  [127:0] ascon_ad_data,
    input  wire         ascon_ad_ready,

    output reg          ascon_pc_valid,
    output reg  [127:0] ascon_pc_data,
    input  wire         ascon_pc_ready,

    input  wire         ascon_pc_valid_out,
    input  wire [127:0] ascon_pc_data_out,
    input  wire [4:0]   ascon_pc_bytes_out,
    input  wire         ascon_pc_last_out,
    output reg          ascon_pc_ready_in
);


    localparam [2:0] IDLE=0, RECEIVE=1, START=2, RUN=3, RESPOND=4, DRAIN=5;
    reg [2:0] state;
    reg [6:0] req_index;
    reg [5:0] resp_index;
    reg [7:0] command, ad_length, pt_length, status;
    reg [127:0] ad_buf, pt_buf, ct_buf, tag_buf;
    integer lane;

    // Stream byte i -> high word first, little endian within each word.
    function integer word_lane;
        input integer i;
        begin
            if (i < 8) word_lane = 64 + 8*i;
            else word_lane = 8*(i-8);
        end
    endfunction

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            req_index <= 0; resp_index <= 0;
            command <= 0; ad_length <= 0; pt_length <= 0; status <= 0;
            ad_buf <= 0; pt_buf <= 0; ct_buf <= 0; tag_buf <= 0;
            tx_data <= 0; tx_valid <= 0;
            ascon_start <= 0; ascon_decrypt <= 0;
            ascon_key <= 0; ascon_nonce <= 0;
            ascon_ad_len <= 0; ascon_pc_len <= 0; ascon_tag_in <= 0;
            ascon_ad_valid <= 0; ascon_pc_valid <= 0;
            ascon_ad_data <= 0; ascon_pc_data <= 0;
            ascon_pc_ready_in <= 0;
        end else begin
            tx_valid <= 0;
            ascon_start <= 0;
            case (state)
                IDLE: if (rx_valid && rx_data == 8'hA5) begin
                    req_index <= 1;
                    ct_buf <= 0; tag_buf <= 0; status <= 0;
                    state <= RECEIVE;
                end
                RECEIVE: if (rx_valid) begin
                    if (req_index == 1) command <= rx_data;
                    else if (req_index == 2) ad_length <= rx_data;
                    else if (req_index == 3) pt_length <= rx_data;
                    else if (req_index < 20)
                        ascon_key[word_lane(req_index-4) +: 8] <= rx_data;
                    else if (req_index < 36)
                        ascon_nonce[word_lane(req_index-20) +: 8] <= rx_data;
                    else if (req_index < 52)
                        ad_buf[(req_index-36)*8 +: 8] <= rx_data;
                    else pt_buf[(req_index-52)*8 +: 8] <= rx_data;
                    if (req_index == 67) state <= START;
                    else req_index <= req_index + 1'b1;
                end
                START: begin
                    resp_index <= 0;
                    if (command != 8'h01) begin
                        status <= 8'h01;
                        state <= RESPOND;
                    end else if (ad_length > 16 || pt_length > 16) begin
                        status <= 8'h02;
                        state <= RESPOND;
                    end else if (!ascon_busy) begin
                        ascon_ad_len <= {24'b0, ad_length};
                        ascon_pc_len <= {24'b0, pt_length};
                        ascon_ad_data <= ad_buf;
                        ascon_pc_data <= pt_buf;
                        ascon_ad_valid <= (ad_length != 0);
                        ascon_pc_valid <= (pt_length != 0);
                        ascon_pc_ready_in <= 1;
                        ascon_start <= 1;
                        state <= RUN;
                    end
                end
                RUN: begin
                    // Hold valid/data until the ready/valid acceptance edge.
                    if (ascon_ad_valid && ascon_ad_ready) ascon_ad_valid <= 0;
                    if (ascon_pc_valid && ascon_pc_ready) ascon_pc_valid <= 0;
                    if (ascon_pc_valid_out && ascon_pc_ready_in) begin
                        for (lane=0; lane<16; lane=lane+1)
                            if (lane < ascon_pc_bytes_out)
                                ct_buf[lane*8 +: 8] <= ascon_pc_data_out[lane*8 +: 8];
                            else ct_buf[lane*8 +: 8] <= 0;
                    end
                    if (ascon_done) begin
                        tag_buf <= ascon_tag_out;
                        ascon_pc_ready_in <= 0;
                        ascon_ad_valid <= 0;
                        ascon_pc_valid <= 0;
                        state <= RESPOND;
                    end
                end
                RESPOND: begin
                    // tx_valid is registered. Its pending pulse must be
                    // consumed before scheduling another byte (busy lags it).
                    if (!tx_busy && !tx_valid) begin
                        if (resp_index == 0) tx_data <= 8'h5A;
                        else if (resp_index == 1) tx_data <= status;
                        else if (resp_index < 18)
                            tx_data <= ct_buf[(resp_index-2)*8 +: 8];
                        else tx_data <= tag_buf[word_lane(resp_index-18) +: 8];
                        tx_valid <= 1;
                        if (resp_index == 33) state <= DRAIN;
                        else resp_index <= resp_index + 1'b1;
                    end
                end
                DRAIN: if (!tx_busy && !tx_valid) state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule

