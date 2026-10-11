`timescale 1ns/1ps
module ascon_buffered_tb;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,config_valid=0,decrypt=0,ad_valid=0,pc_valid=0,admit_valid=0;
    reg response_ready=0,pc_ready_in=0;
    reg [127:0] key=0,nonce=0,tag_in=0,ad_data=0,pc_data_in=0;
    reg [8:0] payload_len=0;
    wire config_ready,ad_ready,pc_ready,admit_ready,busy,response_valid,auth_ok,pc_valid_out,pc_last_out;
    wire [1:0] error_code;
    wire [127:0] tag_out,pc_data_out;
    wire [7:0] elapsed_cycles;
    wire [4:0] pc_bytes_out;
    ascon_buffered dut(.*);
    function [127:0] swap64;
        input [127:0] value;integer i;
        begin for(i=0;i<8;i=i+1) begin
            swap64[(7-i)*8+:8]=value[i*8+:8];
            swap64[64+(7-i)*8+:8]=value[64+i*8+:8];
        end end
    endfunction
    integer f,rc,dir,a,m,ok,j,number=0,cycle=0,accepted,maximum=0;
    reg [127:0] rk,rn,rt,expected_tag,ads[0:2],inputs[0:15],expected[0:15];
    always @(posedge clk) begin
        cycle=cycle+1;
        if(rst_n && admit_valid && admit_ready) accepted=cycle;
        if(rst_n && pc_valid_out && (!auth_ok || error_code!=0))
            $fatal(1,"unauthenticated output escaped");
    end
    initial begin
        repeat(3) @(negedge clk);rst_n=1;
        f=$fopen("build/bounded_cases.vec","r");if(!f)$fatal(1,"missing bounded vectors");
        while(!$feof(f)) begin
            rc=$fscanf(f,"%d",dir);
            if(rc==1) begin
                rc=$fscanf(f,"%h %h %d",rk,rn,a);
                if(a!=48)$fatal(1,"wrong test AD length");
                for(j=0;j<3;j=j+1)rc=$fscanf(f,"%h",ads[j]);
                rc=$fscanf(f,"%d",m);
                for(j=0;j<(m+15)/16;j=j+1)rc=$fscanf(f,"%h",inputs[j]);
                rc=$fscanf(f,"%h",rt);
                for(j=0;j<(m+15)/16;j=j+1)rc=$fscanf(f,"%h",expected[j]);
                rc=$fscanf(f,"%h %d",expected_tag,ok);
                @(negedge clk);key=swap64(rk);nonce=swap64(rn);tag_in=swap64(rt);
                decrypt=dir;payload_len=m;config_valid=1;
                @(negedge clk);config_valid=0;key=~key;nonce=~nonce;tag_in=~tag_in;
                fork
                    begin:load_ad
                        integer i;
                        for(i=0;i<3;i=i+1)begin
                            repeat(1+(i+number)%3)@(negedge clk);
                            ad_data=ads[i];ad_valid=1;
                            @(posedge clk);while(!ad_ready)@(posedge clk);
                            @(negedge clk);ad_valid=0;
                        end
                    end
                    begin:load_pc
                        integer i;
                        for(i=0;i<(m+15)/16;i=i+1)begin
                            repeat(1+(i+number)%2)@(negedge clk);
                            pc_data_in=inputs[i];pc_valid=1;
                            @(posedge clk);while(!pc_ready)@(posedge clk);
                            @(negedge clk);pc_valid=0;
                        end
                    end
                join
                while(!admit_ready)@(negedge clk);
                repeat(2)@(negedge clk);admit_valid=1;
                @(negedge clk);admit_valid=0;
                while(!response_valid)begin
                    if(pc_valid_out)$fatal(1,"output before decision");
                    if(cycle-accepted>=199)$fatal(1,"missed deadline");
                    @(negedge clk);
                end
                if(elapsed_cycles!=cycle-accepted || elapsed_cycles!=59+8*(m/16))
                    $fatal(1,"cycle mismatch length=%0d reported=%0d measured=%0d",m,elapsed_cycles,cycle-accepted);
                if(elapsed_cycles>maximum)maximum=elapsed_cycles;
                if(auth_ok!==ok[0] || error_code!==(ok ? 2'd0:2'd1) || tag_out!==swap64(expected_tag))
                    $fatal(1,"decision mismatch case=%0d length=%0d",number,m);
                repeat(4)begin
                    @(negedge clk);
                    if(!response_valid || pc_valid_out || tag_out!==swap64(expected_tag))
                        $fatal(1,"decision changed while held");
                end
                response_ready=1;@(negedge clk);response_ready=0;
                if(ok)begin
                    for(j=0;j<(m+15)/16;j=j+1)begin
                        while(!pc_valid_out)@(negedge clk);
                        repeat(1+(j+number)%4)begin
                            @(negedge clk);
                            if(!pc_valid_out || pc_data_out!==expected[j])$fatal(1,"output changed while stalled");
                        end
                        if(pc_data_out!==expected[j] || pc_last_out!==(j==(m+15)/16-1) ||
                           pc_bytes_out!==(j==(m+15)/16-1 && m%16 ? m%16:16))
                            $fatal(1,"output mismatch case=%0d beat=%0d",number,j);
                        pc_ready_in=1;@(negedge clk);pc_ready_in=0;
                    end
                end
                if(!config_ready || pc_valid_out)$fatal(1,"did not recover after transaction");
                number=number+1;
            end
        end
        $fclose(f);
        // Invalid profiles must fail admission and never expose stale output.
        for(j=0;j<2;j=j+1)begin
            payload_len=j==0 ? 0:257;config_valid=1;
            @(negedge clk);config_valid=0;
            if(!response_valid || auth_ok || error_code!=2 || admit_ready || pc_valid_out)
                $fatal(1,"invalid profile accepted");
            response_ready=1;@(negedge clk);response_ready=0;
        end
        // Reset while loading, executing, and holding authenticated output.
        for(j=0;j<3;j=j+1)begin
            payload_len=16;decrypt=0;key=0;nonce=0;config_valid=1;
            @(negedge clk);config_valid=0;
            if(j!=0)begin
                ad_valid=1;pc_valid=1;ad_data=0;pc_data_in=0;
                repeat(3)@(negedge clk);ad_valid=0;pc_valid=0;
                while(!admit_ready)@(negedge clk);
                admit_valid=1;@(negedge clk);admit_valid=0;
                if(j==1)repeat(5)@(negedge clk);
                else begin
                    while(!response_valid)@(negedge clk);
                    response_ready=1;@(negedge clk);response_ready=0;
                    if(!pc_valid_out)$fatal(1,"missing drain before reset");
                end
            end
            rst_n=0;@(negedge clk);rst_n=1;@(negedge clk);
            if(!config_ready || busy || response_valid || pc_valid_out || auth_ok || pc_data_out!=0)
                $fatal(1,"reset exposed stale state");
        end
        $display("ALL PASS: %0d buffered reference cases; worst admission-to-decision=%0d cycles",number,maximum);
        $finish;
    end
    initial begin #20000000;$fatal(1,"buffered watchdog");end
endmodule
