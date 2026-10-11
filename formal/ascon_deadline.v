// Actual fast-controller control cone; no cryptographic datapath abstraction.
// Yosys removes the datapath because state values cannot control completion.
module ascon_deadline(input wire clk);
    reg rst_n=0;
    always @(posedge clk) rst_n<=1;
    (* anyconst *) reg [8:0] length;
    (* anyconst *) reg direction;
    (* anyconst *) reg [5:0] ad_length;
    (* anyseq *) reg [127:0] key,nonce,tag,data,ad;
    reg started=0,completed=0;
    reg [7:0] age=0;
    wire done;
    wire [7:0] expected_cycles=8'd26+8*(ad_length==0 ? 0:ad_length/16+1)+{length[8:4],3'b000};
    ascon_controller_fast #(.LENGTH_BITS(9)) dut(
        .clk(clk),.rst_n(rst_n),.start(rst_n && !started),.decrypt(direction),
        .key(key),.nonce(nonce),.tag_in(tag),.ad_len({26'd0,ad_length}),.pc_len({23'd0,length}),
        .busy(),.done(done),.auth_ok(),.tag_out(),.ad_ready(),.ad_valid(1'b1),.ad_data(ad),
        .pc_ready(),.pc_valid(1'b1),.pc_data_in(data),.pc_valid_out(),
        .pc_ready_in(1'b1),.pc_data_out(),.pc_bytes_out(),.pc_last_out());
    always @(posedge clk) begin
        assume(ad_length<=48);
        assume(length>=1 && length<=256);
        if(rst_n) begin
            if(!started)started<=1;
            else if(!completed)begin
                age<=age+1'b1;
                if(done)begin
                    assert(age==expected_cycles);
                    completed<=1;
                end
                assert(age<=186);
            end
        end
    end
endmodule
