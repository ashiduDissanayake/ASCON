// Prove the actual buffered admission-to-response path, including its feeder
// and result capture. Hold the response to isolate a single admitted packet.
module ascon_buffered_deadline(input wire clk);
    reg rst_n=0;always @(posedge clk)rst_n<=1;
    (* anyconst *) reg [8:0] length;
    (* anyconst *) reg direction;
    (* anyconst *) reg [5:0] ad_length;
    (* anyseq *) reg [127:0] key,nonce,tag,data,ad;
    wire admitted,ready,response;
    wire [7:0] elapsed;
    reg started=0,completed=0;
    reg [7:0] age=0;
    reg [7:0] wall=0;
    wire [7:0] expected_cycles=8'd27+8*(ad_length==0 ? 0:ad_length/16+1)+{length[8:4],3'b000};
    ascon_buffered dut(
        .clk(clk),.rst_n(rst_n),.config_valid(1'b1),.config_ready(),
        .decrypt(direction),.key(key),.nonce(nonce),.tag_in(tag),.payload_len(length),.ad_len(ad_length),
        .ad_valid(1'b1),.ad_ready(),.ad_data(ad),
        .pc_valid(1'b1),.pc_ready(),.pc_data_in(data),
        .admit_valid(1'b1),.admit_ready(ready),.busy(),
        .response_valid(response),.response_ready(1'b0),
        .auth_ok(),.error_code(),.tag_out(),.elapsed_cycles(elapsed),
        .pc_valid_out(),.pc_ready_in(1'b0),.pc_data_out(),.pc_bytes_out(),.pc_last_out());
    always @(posedge clk)begin
        assume(ad_length<=48);
        assume(length>=1 && length<=256);
        if(rst_n)begin
            if(wall<215)wall<=wall+1'b1;
            // A concrete always-valid load must reach admission and completion;
            // this prevents an unreachable admission from making the proof vacuous.
            if(wall==215)assert(started && completed);
            if(ready && !started)started<=1;
            else if(started && !completed)begin
                age<=age+1'b1;
                if(response)begin
                    assert(elapsed==expected_cycles);
                    assert(age==expected_cycles);
                    completed<=1;
                end
                assert(age<=187);
            end
        end
    end
endmodule
