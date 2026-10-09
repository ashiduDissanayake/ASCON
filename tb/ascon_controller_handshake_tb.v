`timescale 1ns/1ps
module ascon_controller_handshake_tb;
`ifndef ASCON_DUT
`define ASCON_DUT ascon_controller
`endif
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,start=0,ad_valid=0,pc_valid=0,pc_ready_in=0;
    reg [127:0] ad_data=0,pc_data_in=0;
    wire busy,done,auth_ok,ad_ready,pc_ready,pc_valid_out,pc_last_out;
    wire [127:0] tag_out,pc_data_out; wire [4:0] pc_bytes_out;
    reg [31:0] lfsr=32'h1aceb00c;
    integer ad_index=0,pc_index=0,out_index=0,stalls=0;
    reg holding=0; reg [133:0] held;
    function [127:0] dual_swap_64;
        input [127:0] value; integer i;
        begin
            for(i=0;i<8;i=i+1) begin
                dual_swap_64[(7-i)*8+:8]=value[i*8+:8];
                dual_swap_64[64+(7-i)*8+:8]=value[64+i*8+:8];
            end
        end
    endfunction
    `ASCON_DUT dut(
        .clk(clk),.rst_n(rst_n),.start(start),.decrypt(1'b0),
        .key(dual_swap_64(128'h000102030405060708090A0B0C0D0E0F)),
        .nonce(dual_swap_64(128'h000102030405060708090A0B0C0D0E0F)),
        .ad_len(32),.pc_len(32),.tag_in(128'd0),.busy(busy),.done(done),
        .auth_ok(auth_ok),.tag_out(tag_out),.ad_ready(ad_ready),
        .ad_valid(ad_valid),.ad_data(ad_data),.pc_ready(pc_ready),
        .pc_valid(pc_valid),.pc_data_in(pc_data_in),
        .pc_valid_out(pc_valid_out),.pc_ready_in(pc_ready_in),
        .pc_data_out(pc_data_out),.pc_bytes_out(pc_bytes_out),
        .pc_last_out(pc_last_out));
    always @(negedge clk) begin
        lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
        pc_ready_in=(pc_valid_out && stalls<3) ? 1'b0 : (lfsr[0] & lfsr[3]);
    end
    always @(posedge clk) if(rst_n) begin
        if(holding && (!pc_valid_out || {pc_data_out,pc_bytes_out,pc_last_out}!==held))
            $fatal(1,"output changed while stalled");
        holding=pc_valid_out && !pc_ready_in;
        held={pc_data_out,pc_bytes_out,pc_last_out};
        if(holding) stalls=stalls+1;
        if(ad_valid && ad_ready) begin
            ad_index=ad_index+1;
            if(ad_index==1) ad_data<=128'h1F1E1D1C1B1A19181716151413121110;
            else ad_valid<=0;
        end
        if(pc_valid && pc_ready) begin
            pc_index=pc_index+1;
            if(pc_index==1) pc_data_in<=128'h1F1E1D1C1B1A19181716151413121110;
            else pc_valid<=0;
        end
        if(pc_valid_out && pc_ready_in) begin
            if(out_index==0 && pc_data_out!==128'hBCA97221F2C7CF33231AB5A3276D084C)
                $fatal(1,"first output mismatch");
            if(out_index==1 && pc_data_out!==128'h44EE7BFA4583782D62507ED7D4B888AD)
                $fatal(1,"second output mismatch");
            if(pc_bytes_out!==16 || pc_last_out!==(out_index==1))
                $fatal(1,"output metadata mismatch");
            out_index=out_index+1;
        end
    end
    initial begin
        repeat(3)@(negedge clk);rst_n=1;
        // Both streams assert before ready and remain continuously valid.
        ad_data=128'h0F0E0D0C0B0A09080706050403020100;ad_valid=1;
        pc_data_in=128'h0F0E0D0C0B0A09080706050403020100;pc_valid=1;
        start=1;@(negedge clk);start=0;
        wait(done);#1;
        if(ad_index!=2 || pc_index!=2 || out_index!=2 || stalls==0)
            $fatal(1,"transfer coverage ad=%0d pc=%0d out=%0d stalls=%0d",
                   ad_index,pc_index,out_index,stalls);
        if(tag_out!==dual_swap_64(128'h68915D3F9422289F2349D6A3B4160397))
            $fatal(1,"tag mismatch");
        $display("ALL PASS: early/continuous valid and randomized output stalls");
        $finish;
    end
    initial begin #100000;$fatal(1,"handshake watchdog");end
endmodule
