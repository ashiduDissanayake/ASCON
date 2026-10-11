`timescale 1ns/1ps
// Independent serial-pin driver/decoder, using Python-reference vectors.
module ascon_bounded_uart_tb;
    parameter integer CLKS_PER_BIT=16;
    parameter integer QUICK=0;
    localparam BIT_NS=10*CLKS_PER_BIT;
    reg clk=0;always #5 clk=~clk;
    reg reset=1,rx=1;wire tx;wire [3:0] led;
    ascon_basys3_bounded_top #(.BAUD_RATE(100_000_000/CLKS_PER_BIT),.RX_TIMEOUT_CYCLES(20000)) dut(
        .CLK100MHZ(clk),.btnC(reset),.RsRx(rx),.RsTx(tx),.led(led));
    reg [127:0] rk,rn,rt,et,ads[0:2],inputs[0:15],outputs[0:15];
    reg [7:0] record_bytes[0:18];
    integer f,rc,dir,a,m,ok,i,j,ad_offset,pc_offset,out_offset,finished,checked=0,timing_seen;
    integer accepted_cycle=0,cycle=0;
    always @(posedge clk)begin
        cycle=cycle+1;
        if(dut.u_protocol.u_buffer.core_start)accepted_cycle=cycle;
        if(dut.u_protocol.u_buffer.response_valid &&
           dut.u_protocol.u_buffer.elapsed_cycles!=27+8*(dut.u_protocol.ad_length==0 ? 0:dut.u_protocol.ad_length/16+1)+8*(dut.u_protocol.pc_length/16))
            $fatal(1,"wrong physical integration cycle count");
    end
    task send_byte;
        input [7:0] value;integer b;
        begin
            @(negedge clk);rx=0;#(BIT_NS);
            for(b=0;b<8;b=b+1)begin rx=value[b];#(BIT_NS);end
            rx=1;#(BIT_NS);
        end
    endtask
    task get_byte;
        output [7:0] value;integer b,t;
        begin
            t=0;
            while(tx!==0 && t<50000)begin @(negedge clk);t=t+1;end
            if(tx!==0)$fatal(1,"serial timeout");
            #(BIT_NS/2);
            for(b=0;b<8;b=b+1)begin #(BIT_NS);value[b]=tx;end
            #(BIT_NS);if(tx!==1)$fatal(1,"bad stop bit");
        end
    endtask
    task get_record;
        integer b;
        begin for(b=0;b<19;b=b+1)get_byte(record_bytes[b]);
            if(record_bytes[0]!==8'h5A)$fatal(1,"bad marker");end
    endtask
    task send_u32;
        input [31:0] value;integer b;
        begin for(b=0;b<4;b=b+1)send_byte(value[8*b+:8]);end
    endtask
    task send_header;
        input integer alen,plen;
        integer b;
        begin
            send_byte(8'hA5);send_byte(dir ? 8'h12:8'h11);send_u32(alen);send_u32(plen);
            for(b=0;b<16;b=b+1)send_byte(rk[8*(15-b)+:8]);
            for(b=0;b<16;b=b+1)send_byte(rn[8*(15-b)+:8]);
            for(b=0;b<16;b=b+1)send_byte(rt[8*(15-b)+:8]);
        end
    endtask
    initial begin
        repeat(5)@(negedge clk);reset=0;repeat(5)@(negedge clk);
        f=$fopen("build/bounded_cases.vec","r");if(!f)$fatal(1,"missing UART vectors");
        while(!$feof(f))begin
            rc=$fscanf(f,"%d",dir);
            if(rc==1)begin
                rc=$fscanf(f,"%h %h %d",rk,rn,a);
                for(j=0;j<(a+15)/16;j=j+1)rc=$fscanf(f,"%h",ads[j]);
                rc=$fscanf(f,"%d",m);
                for(j=0;j<(m+15)/16;j=j+1)rc=$fscanf(f,"%h",inputs[j]);
                rc=$fscanf(f,"%h",rt);
                for(j=0;j<(m+15)/16;j=j+1)rc=$fscanf(f,"%h",outputs[j]);
                rc=$fscanf(f,"%h %d",et,ok);
                if((!QUICK && (a==0 || a==1 || a==15 || a==16 || a==17 || a==31 || a==32 || a==33 || a==47 || a==48) && (m==1 || m==16 || m==17 || m==128 || m==256)) ||
                   (QUICK && m==256 && ((a==48 && checked<3) || (a==0 && checked<6) || (a==17 && checked<9))))begin
                    send_header(a,m);get_record;
                    if(record_bytes[1]!=1 || record_bytes[2]!=4 ||
                       {record_bytes[6],record_bytes[5],record_bytes[4],record_bytes[3]}!==32'h34435341 ||
                       {record_bytes[10],record_bytes[9],record_bytes[8],record_bytes[7]}!==256 ||
                       record_bytes[11]!=0 || record_bytes[12]!=48 || record_bytes[16]!=1)$fatal(1,"bad ASC4 capability");
                    ad_offset=0;pc_offset=0;out_offset=0;finished=0;timing_seen=0;
                    while(!finished)begin
                        get_record;
                        case(record_bytes[1])
                            8'h10:begin
                                if(record_bytes[2]!=(a-ad_offset>=16 ? 16:a-ad_offset) || ad_offset>=a || pc_offset)$fatal(1,"AD grant");
                                for(i=0;i<record_bytes[2];i=i+1)send_byte(ads[ad_offset/16][8*i+:8]);
                                ad_offset=ad_offset+record_bytes[2];
                            end
                            8'h11:begin
                                if(ad_offset!=a || record_bytes[2]!=(m-pc_offset>=16 ? 16:m-pc_offset))$fatal(1,"payload grant");
                                for(i=0;i<record_bytes[2];i=i+1)send_byte(inputs[pc_offset/16][8*i+:8]);
                                pc_offset=pc_offset+record_bytes[2];
                            end
                            8'h15:begin
                                if(!ok || timing_seen || pc_offset!=m || record_bytes[2]!=8 ||
                                   {record_bytes[6],record_bytes[5],record_bytes[4],record_bytes[3]}!=27+8*(a==0 ? 0:a/16+1)+8*(m/16) ||
                                   {record_bytes[10],record_bytes[9],record_bytes[8],record_bytes[7]}!=100_000_000)$fatal(1,"timing record");
                                timing_seen=1;
                            end
                            8'h12,8'h14:begin
                                if(!ok || !timing_seen || record_bytes[1]!=(dir ? 8'h14:8'h12) ||
                                   record_bytes[2]!=(m-out_offset>=16 ? 16:m-out_offset))$fatal(1,"premature output");
                                for(i=0;i<record_bytes[2];i=i+1)
                                    if(record_bytes[i+3]!==outputs[out_offset/16][8*i+:8])$fatal(1,"serial output mismatch");
                                for(i=record_bytes[2];i<16;i=i+1)if(record_bytes[i+3]!=0)$fatal(1,"padding");
                                out_offset=out_offset+record_bytes[2];
                            end
                            8'h13:begin
                                if(!ok || out_offset!=m || !timing_seen)$fatal(1,"premature final tag");
                                for(i=0;i<16;i=i+1)if(record_bytes[i+3]!==et[8*(15-i)+:8])$fatal(1,"serial tag mismatch");
                                finished=1;
                            end
                            8'h7F:begin
                                if(ok || record_bytes[2]!=3 || out_offset || timing_seen)$fatal(1,"auth error released output");
                                finished=1;
                            end
                            default:$fatal(1,"unexpected record");
                        endcase
                    end
                    repeat(CLKS_PER_BIT*2)@(negedge clk);checked=checked+1;
                end
            end
        end
        $fclose(f);
        // Incomplete header and invalid length: error, quiet recovery, then
        // a fresh header is recognized without admitting a partial packet.
        send_byte(8'hA5);send_byte(8'h11);get_record;
        if(record_bytes[1]!=8'h7F || record_bytes[2]!=4)$fatal(1,"header timeout recovery");
        repeat(25000)@(negedge clk);
        send_header(48,257);get_record;
        if(record_bytes[1]!=8'h7F || record_bytes[2]!=2)$fatal(1,"invalid length admitted");
        repeat(25000)@(negedge clk);
        send_header(49,16);get_record;
        if(record_bytes[1]!=8'h7F || record_bytes[2]!=2)$fatal(1,"invalid AD length admitted");
        repeat(25000)@(negedge clk);
        send_header(0,16);get_record;
        if(record_bytes[1]!=1 || record_bytes[2]!=4)$fatal(1,"recovery did not accept next header");
        reset=1;repeat(3)@(negedge clk);reset=0;repeat(3)@(negedge clk);
        if(dut.u_protocol.u_buffer.pc_valid_out || dut.u_protocol.execution_busy)$fatal(1,"reset stale output");
        $display("ALL PASS: %0d serial-pin cases, timing records and authentication-gated output",checked);
        $finish;
    end
    initial begin #2000000000;$fatal(1,"UART suite watchdog");end
endmodule
