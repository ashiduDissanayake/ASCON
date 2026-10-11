`timescale 1ns/1ps
// Bounded laboratory execution interface, not a session/replay-policy gateway.
// Load metadata and all bytes, admit, receive decision, then drain output.
// Loading/draining can stall; neither is inside the admission-to-decision bound.
module ascon_buffered (
    input wire clk, rst_n,
    input wire config_valid,
    output wire config_ready,
    input wire decrypt,
    input wire [127:0] key, nonce, tag_in,
    input wire [8:0] payload_len,
    input wire ad_valid,
    output wire ad_ready,
    input wire [127:0] ad_data,
    input wire pc_valid,
    output wire pc_ready,
    input wire [127:0] pc_data_in,
    input wire admit_valid,
    output wire admit_ready,
    output wire busy,
    output wire response_valid,
    input wire response_ready,
    output reg auth_ok,
    output reg [1:0] error_code, // 0 success, 1 auth failure, 2 length, 3 deadline
    output reg [127:0] tag_out,
    output reg [7:0] elapsed_cycles,
    output wire pc_valid_out,
    input wire pc_ready_in,
    output wire [127:0] pc_data_out,
    output wire [4:0] pc_bytes_out,
    output wire pc_last_out
);
    localparam EMPTY=0, LOAD=1, READY=2, RUN=3, RESPONSE=4, DRAIN=5;
    localparam MAX_CYCLES=199;
    reg [2:0] phase;
    reg [127:0] ad_mem[0:2], input_mem[0:15], output_mem[0:15];
    reg [127:0] k, n, expected_tag;
    reg dec;
    reg [8:0] length;
    reg [4:0] beats, pc_load, ad_feed, pc_feed, out_store, out_drain;
    reg [1:0] ad_load;
    reg [7:0] age;
    wire core_start=admit_valid && admit_ready;
    wire core_done, core_auth, core_ad_ready, core_pc_ready, core_out_valid;
    wire [127:0] core_tag, core_out;
    wire [4:0] core_out_bytes;
    wire core_out_last;
    wire core_rst_n=rst_n && phase!=EMPTY && phase!=LOAD;
    assign config_ready=rst_n && phase==EMPTY;
    assign ad_ready=rst_n && phase==LOAD && ad_load<3;
    assign pc_ready=rst_n && phase==LOAD && pc_load<beats;
    assign admit_ready=rst_n && phase==READY;
    assign busy=phase!=EMPTY;
    assign response_valid=rst_n && phase==RESPONSE;
    // No plaintext/ciphertext output is externally visible until the final
    // decision has been acknowledged. Failed decryptions never enter DRAIN.
    assign pc_valid_out=rst_n && phase==DRAIN && auth_ok && out_drain<beats;
    assign pc_data_out=pc_valid_out ? output_mem[out_drain] : 128'd0;
    assign pc_last_out=pc_valid_out && out_drain==beats-1;
    assign pc_bytes_out=!pc_valid_out ? 5'd0 :
        (pc_last_out && length[3:0]!=0 ? {1'b0,length[3:0]} : 5'd16);
    ascon_controller_fast #(.LENGTH_BITS(9)) u_core (
        .clk(clk),.rst_n(core_rst_n),.start(core_start),.decrypt(dec),
        .key(k),.nonce(n),.tag_in(expected_tag),.ad_len(32'd48),
        .pc_len({23'd0,length}),.busy(),.done(core_done),.auth_ok(core_auth),
        .tag_out(core_tag),.ad_ready(core_ad_ready),
        .ad_valid(phase==RUN && ad_feed<3),
        .ad_data(ad_feed<3 ? ad_mem[ad_feed] : 128'd0),
        .pc_ready(core_pc_ready),.pc_valid(phase==RUN && pc_feed<beats),
        .pc_data_in(pc_feed<16 ? input_mem[pc_feed] : 128'd0),
        .pc_valid_out(core_out_valid),.pc_ready_in(phase==RUN && out_store<beats),
        .pc_data_out(core_out),.pc_bytes_out(core_out_bytes),.pc_last_out(core_out_last));
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            phase<=EMPTY;k<=0;n<=0;expected_tag<=0;dec<=0;length<=0;
            beats<=0;pc_load<=0;ad_load<=0;ad_feed<=0;pc_feed<=0;
            out_store<=0;out_drain<=0;age<=0;elapsed_cycles<=0;
            auth_ok<=0;error_code<=0;tag_out<=0;
        end else case(phase)
            EMPTY: if(config_valid && config_ready) begin
                auth_ok<=0;error_code<=0;tag_out<=0;elapsed_cycles<=0;
                if(payload_len==0 || payload_len>256) begin
                    error_code<=2;phase<=RESPONSE;
                end else begin
                    k<=key;n<=nonce;expected_tag<=tag_in;dec<=decrypt;
                    length<=payload_len;beats<=(payload_len+9'd15)>>4;
                    pc_load<=0;ad_load<=0;phase<=LOAD;
                end
            end
            LOAD: begin
                if(ad_valid && ad_ready) begin ad_mem[ad_load]<=ad_data;ad_load<=ad_load+1'b1;end
                if(pc_valid && pc_ready) begin input_mem[pc_load]<=pc_data_in;pc_load<=pc_load+1'b1;end
                if(ad_load==3 && pc_load==beats) phase<=READY;
            end
            READY: if(core_start) begin
                age<=0;ad_feed<=0;pc_feed<=0;out_store<=0;out_drain<=0;phase<=RUN;
            end
            RUN: begin
                age<=age+1'b1;
                if(core_ad_ready && ad_feed<3) ad_feed<=ad_feed+1'b1;
                if(core_pc_ready && pc_feed<beats) pc_feed<=pc_feed+1'b1;
                if(core_out_valid && out_store<beats) begin
                    output_mem[out_store]<=core_out;out_store<=out_store+1'b1;
                end
                if(core_done) begin
                    elapsed_cycles<=age+1'b1;tag_out<=core_tag;
                    auth_ok<=core_auth;error_code<=core_auth ? 0 : 1;phase<=RESPONSE;
                end else if(age==MAX_CYCLES-1) begin
                    elapsed_cycles<=MAX_CYCLES;auth_ok<=0;error_code<=3;phase<=RESPONSE;
                end
            end
            RESPONSE: if(response_ready) begin
                if(auth_ok && error_code==0) begin out_drain<=0;phase<=DRAIN;end
                else begin k<=0;n<=0;expected_tag<=0;phase<=EMPTY;end
            end
            DRAIN: if(pc_valid_out && pc_ready_in) begin
                if(pc_last_out) begin k<=0;n<=0;expected_tag<=0;phase<=EMPTY;end
                else out_drain<=out_drain+1'b1;
            end
            default: begin phase<=EMPTY;auth_ok<=0;error_code<=3;end
        endcase
    end
endmodule
