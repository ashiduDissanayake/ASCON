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


    // UART v3: 58-byte header A5 CMD AD_LEN_LE32 PC_LEN_LE32 KEY16 NONCE16 TAG16.
    // CMD=11 encrypt, 12 decrypt. Tag field is present in both operations.
    // Every FPGA record is 19 bytes: 5A TYPE COUNT PAYLOAD16.
    // TYPE 01=hello, 10=request AD, 11=request data, 12=output, 13=done, 7F=error.
    // PC sends ONLY COUNT raw bytes in response to an input request record.
    // TYPE 14 carries PROVISIONAL plaintext; only DONE confirms authentication.
    // Both operations stream through a 128-bit output register; no message RAM.
    localparam [4:0] IDLE=0, HEADER=1, CHECK=2, LAUNCH=3, DISPATCH=4,
        RX_AD=5, AD_HOLD=6, RX_PC=7, PC_HOLD=8, WAIT_OUT=9,
        FINISH=10, EMIT_DONE=12, TX_RECORD=13, TX_DRAIN=14;
    reg [4:0] state, after_tx;
    reg [6:0] header_index;
    reg [4:0] rx_index, chunk_count, tx_index;
    reg [7:0] command, record_type, record_count;
    reg [127:0] input_buf, output_buf, tag_buf;
    reg [31:0] ad_left, pc_left;
    reg done_seen, authenticated;
    function integer word_lane;
        input integer n;
        begin word_lane = (n < 8) ? 64+8*n : 8*(n-8); end
    endfunction
    function [4:0] chunk_size;
        input [31:0] n;
        begin chunk_size = (n >= 16) ? 5'd16 : n[4:0]; end
    endfunction
    function [127:0] tag_stream;
        input [127:0] value;
        integer n;
        begin
            for(n=0;n<16;n=n+1) tag_stream[8*n +: 8]=value[word_lane(n) +: 8];
        end
    endfunction

    // Called only by this clocked process. Payload is held unchanged while TX
    // serializes it. This is not a second clock or a software function call.
    task send_record;
        input [7:0] kind, count;
        input [127:0] payload;
        input [4:0] continuation;
        begin
            record_type <= kind; record_count <= count; output_buf <= payload;
            tx_index <= 0; after_tx <= continuation; state <= TX_RECORD;
        end
    endtask

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state<=IDLE; after_tx<=IDLE; header_index<=0;
            rx_index<=0;chunk_count<=0;tx_index<=0;
            command<=0;record_type<=0;record_count<=0;
            input_buf<=0;output_buf<=0;tag_buf<=0;
            ad_left<=0;pc_left<=0;
            done_seen<=0;authenticated<=0;
            tx_data<=0;tx_valid<=0;
            ascon_start<=0;ascon_decrypt<=0;ascon_key<=0;ascon_nonce<=0;
            ascon_ad_len<=0;ascon_pc_len<=0;ascon_tag_in<=0;
            ascon_ad_valid<=0;ascon_pc_valid<=0;
            ascon_ad_data<=0;ascon_pc_data<=0;ascon_pc_ready_in<=0;
        end else begin
            tx_valid<=0;ascon_start<=0;ascon_pc_ready_in<=0;
            // Completion can occur while the last ciphertext record is still
            // being transmitted; retain its pulse and tag until FINISH.
            if(ascon_done) begin
                done_seen<=1; authenticated<=ascon_auth_ok; tag_buf<=ascon_tag_out;
            end
            case(state)
                IDLE: if(rx_valid && rx_data==8'hA5) begin
                    header_index<=1;state<=HEADER;
                    done_seen<=0;authenticated<=0;
                    ascon_ad_valid<=0;ascon_pc_valid<=0;
                end
                HEADER: if(rx_valid) begin
                    if(header_index==1) command<=rx_data;
                    else if(header_index<6) ascon_ad_len[8*(header_index-2) +: 8]<=rx_data;
                    else if(header_index<10) ascon_pc_len[8*(header_index-6) +: 8]<=rx_data;
                    else if(header_index<26) ascon_key[word_lane(header_index-10) +: 8]<=rx_data;
                    else if(header_index<42) ascon_nonce[word_lane(header_index-26) +: 8]<=rx_data;
                    else ascon_tag_in[word_lane(header_index-42) +: 8]<=rx_data;
                    if(header_index==57) state<=CHECK;
                    else header_index<=header_index+1'b1;
                end
                CHECK: begin
                    if(command!=8'h11 && command!=8'h12)
                        send_record(8'h7F,8'h01,128'd0,IDLE);
                    else begin
                        ascon_decrypt<=(command==8'h12);
                        ad_left<=ascon_ad_len;pc_left<=ascon_pc_len;
                        // Hello: ASC3, max length LE32, provisional-output flag, zeros.
                        send_record(8'h01,8'd3,{56'd0,8'd1,32'hFFFFFFFF,32'h33435341},LAUNCH);
                    end
                end
                LAUNCH: if(!ascon_busy) begin
                    ascon_start<=1;done_seen<=0;state<=DISPATCH;
                end
                DISPATCH: begin
                    input_buf<=0;rx_index<=0;
                    if(ad_left!=0) begin
                        chunk_count<=chunk_size(ad_left);
                        send_record(8'h10,{3'd0,chunk_size(ad_left)},128'd0,RX_AD);
                    end else if(pc_left!=0) begin
                        chunk_count<=chunk_size(pc_left);
                        send_record(8'h11,{3'd0,chunk_size(pc_left)},128'd0,RX_PC);
                    end else state<=FINISH;
                end
                RX_AD: if(rx_valid) begin
                    input_buf[8*rx_index +: 8]<=rx_data;
                    if(rx_index+1==chunk_count) state<=AD_HOLD;
                    else rx_index<=rx_index+1'b1;
                end
                AD_HOLD: begin
                    ascon_ad_data<=input_buf;
                    ascon_ad_valid<=1;
                    if(ascon_ad_valid && ascon_ad_ready) begin
                        ascon_ad_valid<=0;ad_left<=ad_left-chunk_count;state<=DISPATCH;
                    end
                end
                RX_PC: if(rx_valid) begin
                    input_buf[8*rx_index +: 8]<=rx_data;
                    if(rx_index+1==chunk_count) state<=PC_HOLD;
                    else rx_index<=rx_index+1'b1;
                end
                PC_HOLD: begin
                    ascon_pc_data<=input_buf;
                    ascon_pc_valid<=1;
                    if(ascon_pc_valid && ascon_pc_ready) begin
                        ascon_pc_valid<=0;pc_left<=pc_left-chunk_count;state<=WAIT_OUT;
                    end
                end
                WAIT_OUT: if(ascon_pc_valid_out) begin
                    // Capture once. Core observes this ready pulse next edge;
                    // we cannot capture its next beat until DISPATCH returns.
                    ascon_pc_ready_in<=1;
                    send_record(ascon_decrypt ? 8'h14 : 8'h12,
                                {3'd0,ascon_pc_bytes_out},ascon_pc_data_out,DISPATCH);
                end
                FINISH: if(done_seen) begin
                    if(ascon_decrypt && !authenticated)
                        send_record(8'h7F,8'h03,128'd0,IDLE);
                    else state<=EMIT_DONE;
                end
                EMIT_DONE: send_record(8'h13,8'd16,tag_stream(tag_buf),IDLE);
                TX_RECORD: if(!tx_busy && !tx_valid) begin
                    if(tx_index==0) tx_data<=8'h5A;
                    else if(tx_index==1) tx_data<=record_type;
                    else if(tx_index==2) tx_data<=record_count;
                    else tx_data<=output_buf[8*(tx_index-3) +: 8];
                    tx_valid<=1;
                    if(tx_index==18) state<=TX_DRAIN;
                    else tx_index<=tx_index+1'b1;
                end
                TX_DRAIN: if(!tx_busy && !tx_valid) state<=after_tx;
                default: state<=IDLE;
            endcase
        end
    end
endmodule
