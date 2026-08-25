`timescale 1ns/1ps

module ascon_keyxor_tb;
    reg [63:0] x0_in, x1_in, x2_in, x3_in, x4_in;
    reg [127:0] key;
    wire [63:0] x0_out, x1_out, x2_out, x3_out, x4_out;
    
    reg [63:0] x0_exp, x1_exp, x2_exp, x3_exp, x4_exp;
    
    integer vector_file;
    integer read_count;
    integer vector_number;
    integer pass_count;
    integer fail_count;
    
    ascon_keyxor dut (
        .x0_in(x0_in),
        .x1_in(x1_in),
        .x2_in(x2_in),
        .x3_in(x3_in),
        .x4_in(x4_in),
        .key(key),
        .x0_out(x0_out),
        .x1_out(x1_out),
        .x2_out(x2_out),
        .x3_out(x3_out),
        .x4_out(x4_out)
    );

initial begin
        $dumpfile("dump_keyxor.vcd");
        $dumpvars(0, ascon_keyxor_tb);

        // Initialize counters
        pass_count = 0;
        fail_count = 0;
        vector_number = 1;

        // Open the file
        vector_file = $fopen("vectors/keyxor_cases.vec", "r");
        if (vector_file == 0)
            $fatal(1, "could not open vectors/keyxor_cases.vec");

        // Loop through the file
        while (!$feof(vector_file)) begin
            // Grab exactly 11 hexadecimal strings from a single row
            read_count = $fscanf(vector_file, "%h %h %h %h %h %h %h %h %h %h %h\n", 
                                 x0_in, x1_in, x2_in, x3_in, x4_in, // 5 inputs
                                 key,                               // 1 key
                                 x0_exp, x1_exp, x2_exp, x3_exp, x4_exp); // 5 expected outputs

            // If we successfully read a full line of 11 items...
            if (read_count == 11) begin
                #1; // Wait 1ns for the XOR gates to settle

                // Check actual output wires against the expected registers
                if ((x0_out === x0_exp) &&
                    (x1_out === x1_exp) &&
                    (x2_out === x2_exp) &&
                    (x3_out === x3_exp) &&
                    (x4_out === x4_exp)) begin
                    
                    $display("PASS vector %0d", vector_number);
                    pass_count = pass_count + 1;
                end else begin
                    $display("FAIL vector %0d", vector_number);
                    $display("  expected: %016h %016h %016h %016h %016h", x0_exp, x1_exp, x2_exp, x3_exp, x4_exp);
                    $display("  actual  : %016h %016h %016h %016h %016h", x0_out, x1_out, x2_out, x3_out, x4_out);
                    fail_count = fail_count + 1;
                end
                
                vector_number = vector_number + 1;
            end
        end

        // Clean up and print summary
        $fclose(vector_file);
        $display("SUMMARY vectors=%0d pass=%0d fail=%0d", vector_number-1, pass_count, fail_count);
        
        if (fail_count != 0) begin
            $display("verification failed");
        end
        $finish;
    end
endmodule