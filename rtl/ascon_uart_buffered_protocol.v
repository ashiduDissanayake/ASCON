`timescale 1ns/1ps
// UART v4 preserves the header/grant records but buffers the complete packet.
// ASC4 hello: AD 0..48 bytes, payload 1..256, authenticated output only.
module ascon_uart_buffered_protocol #(
    parameter integer CLK_FREQ_HZ=100_000_000,
    parameter integer RX_TIMEOUT_CYCLES=10_000_000
)(
    input wire clk,rst_n,
    input wire [7:0] rx_data,
    input wire rx_valid,
    output reg [7:0] tx_data,
    output reg tx_valid,
    input wire tx_busy,
    output wire execution_busy,
    output wire execution_done
);
    localparam IDLE=0,HEADER=1,CHECK=2,CONFIG=3,HELLO=4,DISPATCH=5,
        RX_AD=6,AD_HOLD=7,RX_PC=8,PC_HOLD=9,ADMIT=10,DECISION=11,
        WAIT_OUT=12,FINISH=13,TX_RECORD=14,TX_DRAIN=15,RECOVER=16;
    reg [4:0] phase,after_tx;
    reg [6:0] header_index;
    reg [4:0] rx_index,chunk_count,tx_index;
    reg [7:0] command,record_type,record_count;
    reg [31:0] ad_length,pc_length,ad_left,pc_left,idle_cycles;
    reg [127:0] key,nonce,expected_tag,input_buf,output_buf,final_tag;
    reg buffer_reset;
    localparam [31:0] CLOCK_HZ=CLK_FREQ_HZ;
    wire config_ready,ad_ready,pc_ready,admit_ready,response_valid,auth_ok,pc_valid_out;
    wire [1:0] error_code;
    wire [7:0] elapsed_cycles;
    wire [127:0] tag_out,pc_data_out;
    wire [4:0] pc_bytes_out;
    wire pc_last_out;
    wire receiving=phase==HEADER || phase==RX_AD || phase==RX_PC;
    assign execution_busy=phase==DECISION;
    assign execution_done=phase==DECISION && response_valid;
    ascon_buffered u_buffer(
        .clk(clk),.rst_n(rst_n && !buffer_reset),
        .config_valid(phase==CONFIG),.config_ready(config_ready),
        .decrypt(command==8'h12),.key(key),.nonce(nonce),.tag_in(expected_tag),
        .payload_len(pc_length[8:0]),.ad_len(ad_length[5:0]),
        .ad_valid(phase==AD_HOLD),.ad_ready(ad_ready),.ad_data(input_buf),
        .pc_valid(phase==PC_HOLD),.pc_ready(pc_ready),.pc_data_in(input_buf),
        .admit_valid(phase==ADMIT),.admit_ready(admit_ready),.busy(),
        .response_valid(response_valid),.response_ready(phase==DECISION),
        .auth_ok(auth_ok),.error_code(error_code),.tag_out(tag_out),.elapsed_cycles(elapsed_cycles),
        .pc_valid_out(pc_valid_out),.pc_ready_in(phase==WAIT_OUT),
        .pc_data_out(pc_data_out),.pc_bytes_out(pc_bytes_out),.pc_last_out(pc_last_out));
    function integer word_lane;
        input integer i;
        begin word_lane=i<8 ? 64+8*i : 8*(i-8);end
    endfunction
    function [127:0] stream_tag;
        input [127:0] value;integer i;
        begin for(i=0;i<16;i=i+1)stream_tag[8*i+:8]=value[word_lane(i)+:8];end
    endfunction
    task send_record;
        input [7:0] kind,count;
        input [127:0] payload;
        input [4:0] next_phase;
        begin
            record_type<=kind;record_count<=count;output_buf<=payload;
            tx_index<=0;after_tx<=next_phase;phase<=TX_RECORD;
        end
    endtask
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n)begin
            phase<=IDLE;after_tx<=IDLE;header_index<=0;rx_index<=0;chunk_count<=0;
            tx_index<=0;command<=0;record_type<=0;record_count<=0;ad_length<=0;pc_length<=0;
            ad_left<=0;pc_left<=0;idle_cycles<=0;key<=0;nonce<=0;expected_tag<=0;
            input_buf<=0;output_buf<=0;final_tag<=0;buffer_reset<=1;tx_data<=0;tx_valid<=0;
        end else begin
            tx_valid<=0;
            if(rx_valid || (!receiving && phase!=RECOVER))idle_cycles<=0;
            else if(idle_cycles<RX_TIMEOUT_CYCLES)idle_cycles<=idle_cycles+1;
            if(receiving && !rx_valid && idle_cycles>=RX_TIMEOUT_CYCLES-1)begin
                buffer_reset<=1;key<=0;nonce<=0;expected_tag<=0;input_buf<=0;idle_cycles<=0;
                send_record(8'h7F,8'h04,128'd0,RECOVER);
            end else case(phase)
                IDLE:if(rx_valid && rx_data==8'hA5)begin
                    header_index<=1;buffer_reset<=0;phase<=HEADER;
                end
                HEADER:if(rx_valid)begin
                    if(header_index==1)command<=rx_data;
                    else if(header_index<6)ad_length[8*(header_index-2)+:8]<=rx_data;
                    else if(header_index<10)pc_length[8*(header_index-6)+:8]<=rx_data;
                    else if(header_index<26)key[word_lane(header_index-10)+:8]<=rx_data;
                    else if(header_index<42)nonce[word_lane(header_index-26)+:8]<=rx_data;
                    else expected_tag[word_lane(header_index-42)+:8]<=rx_data;
                    if(header_index==57)phase<=CHECK;
                    else header_index<=header_index+1'b1;
                end
                CHECK:begin
                    if(command!=8'h11 && command!=8'h12)begin
                        buffer_reset<=1;send_record(8'h7F,8'h01,128'd0,RECOVER);
                    end else if(ad_length>48 || pc_length==0 || pc_length>256)begin
                        buffer_reset<=1;send_record(8'h7F,8'h02,128'd0,RECOVER);
                    end else begin ad_left<=ad_length;pc_left<=pc_length;phase<=CONFIG;end
                end
                CONFIG:if(config_ready)phase<=HELLO;
                // Payload byte 13 advertises variable AD; old firmware used 0.
                HELLO:send_record(8'h01,8'd4,{16'd0,8'd1,32'd48,8'd0,32'd256,32'h34435341},DISPATCH);
                DISPATCH:begin
                    input_buf<=0;rx_index<=0;
                    if(ad_left!=0)begin
                        chunk_count<=ad_left>=16 ? 16 : ad_left[4:0];
                        send_record(8'h10,ad_left>=16 ? 8'd16 : ad_left[7:0],128'd0,RX_AD);
                    end else if(pc_left!=0)begin
                        chunk_count<=pc_left>=16 ? 16 : pc_left[4:0];
                        send_record(8'h11,pc_left>=16 ? 8'd16 : pc_left[7:0],128'd0,RX_PC);
                    end else if(admit_ready)phase<=ADMIT;
                end
                RX_AD,RX_PC:if(rx_valid)begin
                    input_buf[8*rx_index+:8]<=rx_data;
                    if(rx_index+1==chunk_count)phase<=phase==RX_AD ? AD_HOLD : PC_HOLD;
                    else rx_index<=rx_index+1'b1;
                end
                AD_HOLD:if(ad_ready)begin ad_left<=ad_left-chunk_count;phase<=DISPATCH;end
                PC_HOLD:if(pc_ready)begin pc_left<=pc_left-chunk_count;phase<=DISPATCH;end
                ADMIT:if(admit_ready)phase<=DECISION;
                DECISION:if(response_valid)begin
                    final_tag<=tag_out;
                    if(error_code!=0)
                        send_record(8'h7F,error_code==1 ? 8'h03 : 8'h05,128'd0,IDLE);
                    else
                        // Timing is hardware service cycles, not host round-trip time.
                        send_record(8'h15,8'd8,{64'd0,CLOCK_HZ,24'd0,elapsed_cycles},WAIT_OUT);
                end
                WAIT_OUT:if(pc_valid_out)
                    send_record(command==8'h12 ? 8'h14 : 8'h12,
                        {3'd0,pc_bytes_out},pc_data_out,pc_last_out ? FINISH : WAIT_OUT);
                FINISH:begin
                    key<=0;nonce<=0;expected_tag<=0;
                    send_record(8'h13,8'd16,stream_tag(final_tag),IDLE);
                end
                TX_RECORD:if(!tx_busy && !tx_valid)begin
                    if(tx_index==0)tx_data<=8'h5A;
                    else if(tx_index==1)tx_data<=record_type;
                    else if(tx_index==2)tx_data<=record_count;
                    else tx_data<=output_buf[8*(tx_index-3)+:8];
                    tx_valid<=1;
                    if(tx_index==18)phase<=TX_DRAIN;
                    else tx_index<=tx_index+1'b1;
                end
                TX_DRAIN:if(!tx_busy && !tx_valid)phase<=after_tx;
                RECOVER:if(!rx_valid && idle_cycles>=RX_TIMEOUT_CYCLES-1)begin
                    phase<=IDLE;idle_cycles<=0;
                end
                default:begin phase<=IDLE;buffer_reset<=1;end
            endcase
        end
    end
endmodule
