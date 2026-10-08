`timescale 1ns/1ps
module ascon_uart_recovery_tb;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0,rx_valid=0; reg [7:0] rx_data=0;
    wire [7:0] tx_data; wire tx_valid,abort_op,start;
    reg core_busy=0;
    integer aborts=0, starts=0, errors=0, index=0;
    reg [7:0] record_data[0:18];
    ascon_uart_protocol #(.RX_TIMEOUT_CYCLES(32),.MAX_LENGTH(8192)) dut(
        .clk(clk),.rst_n(rst_n),.rx_data(rx_data),.rx_valid(rx_valid),
        .tx_data(tx_data),.tx_valid(tx_valid),.tx_busy(1'b0),
        .ascon_abort(abort_op),.ascon_start(start),.ascon_busy(core_busy),
        .ascon_done(1'b0),.ascon_auth_ok(1'b0),.ascon_tag_out(128'd0),
        .ascon_ad_ready(1'b1),.ascon_pc_ready(1'b1),
        .ascon_pc_valid_out(1'b0),.ascon_pc_data_out(128'd0),
        .ascon_pc_bytes_out(5'd0),.ascon_pc_last_out(1'b0));
    always @(posedge clk) begin
        if(start) begin starts=starts+1;core_busy<=1;end
        if(abort_op) begin aborts=aborts+1;core_busy<=0;end
        if(tx_valid) begin
            record_data[index]=tx_data;
            if(index==18) begin
                if(record_data[0]!==8'h5a)$fatal(1,"record marker");
                if(record_data[1]==8'h7f) begin
                    if(record_data[2]!=4 && record_data[2]!=2)$fatal(1,"error code");
                    errors=errors+1;
                end
                index=0;
            end else index=index+1;
        end
    end
    task byte_in;
        input [7:0] value;
        begin @(negedge clk);rx_data=value;rx_valid=1;
              @(negedge clk);rx_valid=0;end
    endtask
    task header;
        input [31:0] alen,plen;
        integer i;
        begin
            byte_in(8'ha5);byte_in(8'h11);
            for(i=0;i<4;i=i+1)byte_in(alen[8*i+:8]);
            for(i=0;i<4;i=i+1)byte_in(plen[8*i+:8]);
            for(i=0;i<48;i=i+1)byte_in(0);
        end
    endtask
    initial begin
        repeat(4)@(negedge clk);rst_n=1;
        byte_in(8'ha5);byte_in(8'h11);
        repeat(150)@(negedge clk);
        if(aborts!=1 || errors!=1 || dut.state!=0)$fatal(1,"header timeout");
        header(1,0);
        repeat(220)@(negedge clk);
        if(aborts!=2 || starts!=1 || core_busy || dut.state!=0)$fatal(1,"AD timeout");
        header(0,1);
        repeat(220)@(negedge clk);
        if(aborts!=3 || starts!=2 || core_busy || dut.state!=0)$fatal(1,"payload timeout");
        header(0,8193);
        repeat(150)@(negedge clk);
        if(starts!=2 || errors!=4 || dut.state!=0)$fatal(1,"length bound");
        header(0,1);
        wait(dut.state==7);byte_in(8'h55);
        repeat(10)@(negedge clk);
        if(starts!=3 || dut.ascon_pc_data[7:0]!=8'h55)$fatal(1,"next transaction");
        rst_n=0;core_busy=0;repeat(2)@(negedge clk);rst_n=1;
        if(dut.ascon_pc_valid || dut.done_seen)$fatal(1,"reset stale state");
        $display("ALL PASS: header/AD/payload timeout, length bound, recovery, reset");
        $finish;
    end
    initial begin #100000; $fatal(1,"recovery watchdog");end
endmodule
