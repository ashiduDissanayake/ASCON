`timescale 1ns/1ps
// One shared round per cycle. Absorb/key XORs feed that same round rather
// than launching a second FSM. Stream outputs are provisional on decrypt.
module ascon_controller_fast #(
    parameter integer LENGTH_BITS=32
)(
    input wire clk, rst_n, start, decrypt,
    input wire [127:0] key, nonce, tag_in,
    input wire [31:0] ad_len, pc_len,
    output reg busy, done, auth_ok,
    output reg [127:0] tag_out,
    output wire ad_ready,
    input wire ad_valid,
    input wire [127:0] ad_data,
    output wire pc_ready,
    input wire pc_valid,
    input wire [127:0] pc_data_in,
    output reg pc_valid_out,
    input wire pc_ready_in,
    output reg [127:0] pc_data_out,
    output reg [4:0] pc_bytes_out,
    output reg pc_last_out
);
    localparam IDLE=0, INIT=1, AD=2, AD_ROUND=3, DOMSEP=4,
               PC=5, PC_ROUND=6, PC_PAD=7, FIN=8;
    reg [3:0] phase, round_index;
    reg [319:0] s;
    reg [127:0] k, expected_tag;
    reg dec, last_block, extra_ad;
    // Narrow only in the bounded wrapper, whose admission validates lengths.
    reg [LENGTH_BITS-1:0] ad_left, pc_left;
    wire [4:0] ad_bytes = ad_left >= 16 ? 5'd16 : ad_left[4:0];
    wire [4:0] pc_bytes = pc_left >= 16 ? 5'd16 : pc_left[4:0];
    wire output_space = !pc_valid_out || pc_ready_in;
    assign ad_ready = rst_n && phase==AD && ad_left!=0;
    assign pc_ready = rst_n && phase==PC && pc_left!=0 && output_space;

    // Low lanes contain stream bytes. Padding byte is 01; unused lanes
    // never enter the state, including the synthetic exact-rate tail.
    function [127:0] absorb_ad;
        input [127:0] old_rate, data;
        input [4:0] n;
        integer i;
        begin
            absorb_ad=old_rate;
            for(i=0;i<16;i=i+1)
                if(i<n) absorb_ad[8*i+:8]=old_rate[8*i+:8]^data[8*i+:8];
                else if(i==n) absorb_ad[8*i+:8]=old_rate[8*i+:8]^8'h01;
        end
    endfunction
    function [255:0] absorb_pc;
        input [127:0] old_rate, data;
        input [4:0] n;
        input direction;
        reg [127:0] updated, result;
        integer i;
        begin
            updated=old_rate; result=0;
            for(i=0;i<16;i=i+1) begin
                if(i<n) begin
                    result[8*i+:8]=old_rate[8*i+:8]^data[8*i+:8];
                    updated[8*i+:8]=direction ? data[8*i+:8] : result[8*i+:8];
                end else if(i==n) updated[8*i+:8]=old_rate[8*i+:8]^8'h01;
            end
            absorb_pc={updated,result};
        end
    endfunction
    wire [127:0] ad_rate=absorb_ad({s[255:192],s[319:256]},ad_data,ad_bytes);
    wire [255:0] pc_update=absorb_pc({s[255:192],s[319:256]},pc_data_in,pc_bytes,dec);
    reg [319:0] round_in;
    always @* begin
        round_in=s;
        if(phase==AD) begin
            round_in[319:256]=ad_rate[63:0];
            round_in[255:192]=ad_rate[127:64];
        end
        if(phase==PC) begin
            round_in[319:256]=pc_update[191:128];
            round_in[255:192]=pc_update[255:192];
        end
        if(phase==FIN && round_index==0) begin
            round_in[191:128]=s[191:128]^k[127:64];
            round_in[127:64]=s[127:64]^k[63:0];
        end
    end
    wire [3:0] const_idx = (phase==INIT || phase==FIN)
                          ? 4'd4+round_index : 4'd8+round_index;
    wire [319:0] round_out;
    ascon_round u_round(
        .const_idx(const_idx),
        .x0_in(round_in[319:256]),.x1_in(round_in[255:192]),
        .x2_in(round_in[191:128]),.x3_in(round_in[127:64]),.x4_in(round_in[63:0]),
        .x0_out(round_out[319:256]),.x1_out(round_out[255:192]),
        .x2_out(round_out[191:128]),.x3_out(round_out[127:64]),.x4_out(round_out[63:0]));
    wire [127:0] final_tag=round_out[127:0]^k;

    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            phase<=IDLE;round_index<=0;s<=0;k<=0;expected_tag<=0;
            dec<=0;last_block<=0;extra_ad<=0;ad_left<=0;pc_left<=0;
            busy<=0;done<=0;auth_ok<=0;tag_out<=0;
            pc_valid_out<=0;pc_data_out<=0;pc_bytes_out<=0;pc_last_out<=0;
        end else begin
            done<=0;
            if(pc_valid_out && pc_ready_in) pc_valid_out<=0;
            case(phase)
                IDLE: if(start) begin
                    s<={64'h00001000808c0001,key,nonce};
                    k<=key;expected_tag<=tag_in;dec<=decrypt;
                    ad_left<=ad_len;pc_left<=pc_len;
                    busy<=1;auth_ok<=0;round_index<=0;extra_ad<=0;phase<=INIT;
                end
                INIT: begin
                    s<=round_out;round_index<=round_index+1'b1;
                    if(round_index==11) begin
                        s[127:0]<=round_out[127:0]^k;
                        round_index<=0;phase<=ad_left==0 ? DOMSEP : AD;
                    end
                end
                AD: if(ad_left==0 || (ad_valid && ad_ready)) begin
                    s<=round_out;round_index<=1;phase<=AD_ROUND;
                    last_block<=ad_left<=16;
                    extra_ad<=ad_left==16;
                    ad_left<=ad_left>16 ? ad_left-16 : 0;
                end
                AD_ROUND: begin
                    s<=round_out;round_index<=round_index+1'b1;
                    if(round_index==7) begin
                        round_index<=0;
                        phase<=(!last_block || extra_ad) ? AD : DOMSEP;
                    end
                end
                DOMSEP: begin s[63]<=~s[63];phase<=PC;end
                PC: if(output_space && (pc_left==0 || (pc_valid && pc_ready))) begin
                    if(pc_left!=0) begin
                        pc_valid_out<=1;pc_data_out<=pc_update[127:0];
                        pc_bytes_out<=pc_bytes;pc_last_out<=pc_left<=16;
                    end
                    pc_left<=pc_left>16 ? pc_left-16 : 0;
                    last_block<=pc_left<=16;
                    if(pc_bytes==16) begin
                        s<=round_out;round_index<=1;phase<=PC_ROUND;
                    end else begin
                        s[319:256]<=pc_update[191:128];
                        s[255:192]<=pc_update[255:192];
                        round_index<=0;phase<=FIN;
                    end
                end
                PC_ROUND: begin
                    s<=round_out;round_index<=round_index+1'b1;
                    if(round_index==7) begin
                        round_index<=0;phase<=last_block ? PC_PAD : PC;
                    end
                end
                PC_PAD: if(output_space) begin
                    s[256]<=~s[256];round_index<=0;phase<=FIN;
                end
                FIN: if(round_index!=0 || output_space) begin
                    s<=round_out;round_index<=round_index+1'b1;
                    if(round_index==11) begin
                        tag_out<=final_tag;auth_ok<=!dec || final_tag==expected_tag;
                        busy<=0;done<=1;round_index<=0;phase<=IDLE;
                    end
                end
                default: begin phase<=IDLE;busy<=0;pc_valid_out<=0;end
            endcase
        end
    end
endmodule
