`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 08/27/2026 10:50:34 PM
// Design Name: 
// Module Name: ascon_single_controller_tb
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
//////////////////////////////////////////////////////////////////////////////////



module ascon_single_controller_tb;
    reg clk, rst_n;

    reg          start, decrypt;
    reg  [127:0] key, nonce, tag_in;
    reg  [31:0]  ad_len, pc_len;
    wire         busy, done, auth_ok;
    wire [127:0] tag_out;

    reg          ad_valid;
    reg  [127:0] ad_data;
    wire         ad_ready;

    reg          pc_valid;
    reg  [127:0] pc_data_in;
    wire         pc_ready;

    wire         pc_valid_out;
    reg          pc_ready_in;
    wire [127:0] pc_data_out;
    wire [4:0]   pc_bytes_out;
    wire         pc_last_out;
    
    // --- ENDIANNESS SWAP TOOLS ---
    function [127:0] dual_swap_64;
        input [127:0] in;
        integer i;
        begin
            for (i = 0; i < 8; i = i + 1) begin
                dual_swap_64[(7-i)*8 +: 8] = in[i*8 +: 8];
                dual_swap_64[64 + (7-i)*8 +: 8] = in[64 + i*8 +: 8];
            end
        end
    endfunction

    function [127:0] full_swap_128;
        input [127:0] in;
        integer i;
        begin
            for (i = 0; i < 16; i = i + 1) begin
                full_swap_128[(15-i)*8 +: 8] = in[i*8 +: 8];
            end
        end
    endfunction

    // --- CONTROLLER INSTANTIATION ---
    ascon_controller dut (
        .clk         (clk),
        .rst_n       (rst_n),
        .start       (start),
        .decrypt     (decrypt),
        .key         (dual_swap_64(key)),       // 64-bit swap for math logic
        .nonce       (dual_swap_64(nonce)),     // 64-bit swap for math logic
        .tag_in      (dual_swap_64(tag_in)),
        .ad_len      (ad_len),
        .pc_len      (pc_len),
        .busy        (busy),
        .done        (done),
        .auth_ok     (auth_ok),
        .tag_out     (tag_out),
        .ad_ready    (ad_ready),
        .ad_valid    (ad_valid),
        .ad_data     (full_swap_128(ad_data)),    // 128-bit swap for streams
        .pc_ready    (pc_ready),
        .pc_valid    (pc_valid),
        .pc_data_in  (full_swap_128(pc_data_in)), // 128-bit swap for streams
        .pc_valid_out(pc_valid_out),
        .pc_ready_in (pc_ready_in),
        .pc_data_out (pc_data_out),
        .pc_bytes_out(pc_bytes_out),
        .pc_last_out (pc_last_out)
    );

    always #5 clk = ~clk;

    // Registers to hold expected outputs for checking
    reg [127:0] exp_ct;
    reg [127:0] exp_tag;
    reg [127:0] actual_ct;

    initial begin


        // 1. Initial State
        clk = 0; rst_n = 0; start = 0; decrypt = 0;
        ad_valid = 0; pc_valid = 0; pc_ready_in = 1;
        
        // 2. Load exact values from the Python Script
        key        = 128'h34dbed81998f6ddd1801f61428193acd;
        nonce      = 128'h0473cbdc0e7d828a7cef3303ce348e44;
        
        // "ASCON" = 5 bytes (0x4153434f4e). Padded with 0s to make 128 bits
        ad_len     = 5;
        ad_data    = 128'h4153434f4e0000000000000000000000;
        
        // "ascon" = 5 bytes (0x6173636f6e). Padded with 0s to make 128 bits
        pc_len     = 5;
        pc_data_in = 128'h6173636f6e0000000000000000000000;
        
        // Expected Ciphertext and Tag from Python
        exp_ct     = 128'hadb0d7c90e0000000000000000000000;
        exp_tag    = 128'h3008f8981f803a7b1db2302b6df4697a;

        #12; rst_n = 1; #10;

        // 3. Pulse Start
        start = 1; #10; start = 0;

        // 4. Run the data streams in parallel
        fork
            // Send Associated Data
            begin
                while (!ad_ready) #10;
                ad_valid = 1; #10; ad_valid = 0;
            end
            
            // Send Plaintext
            begin
                while (!pc_ready) #10;
                pc_valid = 1; #10; pc_valid = 0;
            end
            
            // Capture Ciphertext Output
            begin
                while (!done) begin
                    #10;
                    if (pc_valid_out) begin
                        actual_ct = full_swap_128(pc_data_out);
                    end
                end
            end
        join

        #1; // Wait for combinational logic to settle on the done cycle

        // 5. Check Results!
        $display("----------------------------------------");
        $display("ASCON ENCRYPTION TEST");
        $display("----------------------------------------");
        
        // Check Ciphertext
        if (actual_ct[127:88] === exp_ct[127:88]) // Only checking top 5 bytes (40 bits)
            $display("PASS: Ciphertext matched -> %h", actual_ct[127:88]);
        else begin
            $display("FAIL: Ciphertext mismatch!");
            $display("  Expected: %h", exp_ct[127:88]);
            $display("  Actual:   %h", actual_ct[127:88]);
        end
        
        // Check Tag
        if (tag_out === dual_swap_64(exp_tag))
            $display("PASS: Tag matched -> %h", exp_tag);
        else begin
            $display("FAIL: Tag mismatch!");
            $display("  Expected: %h", exp_tag);
            $display("  Actual:   %h", dual_swap_64(tag_out));
        end
        $display("----------------------------------------");

        $finish;
    end
endmodule
