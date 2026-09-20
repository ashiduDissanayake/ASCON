`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 09/20/2026 05:58:55 PM
// Design Name: 
// Module Name: uart_tx
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


// 8N1 UART transmitter.
// FPGA clock: 100 MHz
// Default baud: 115200
module uart_tx #(
    parameter integer CLK_FREQ_HZ = 100_000_000,
    parameter integer BAUD_RATE   = 115200
) (
    input  wire      clk,
    input  wire      rst_n,
    input  wire [7:0] data_in,
    input  wire       data_valid,
    output reg        tx,
    output reg        busy
);

    localparam integer CLKS_PER_BIT = CLK_FREQ_HZ / BAUD_RATE;

    reg [31:0] clk_count;
    reg [3:0]  bit_index;
    reg [9:0]  tx_shift;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            clk_count <= 0;
            bit_index <= 0;
            tx_shift  <= 10'b1111111111;
            tx        <= 1'b1;
            busy      <= 1'b0;
        end else begin
            if (!busy) begin
                tx <= 1'b1;
                if (data_valid) begin
                    // {stop, data[7:0], start}; LSB is transmitted first.
                    tx_shift  <= {1'b1, data_in, 1'b0};
                    clk_count <= 0;
                    bit_index <= 0;
                    busy      <= 1'b1;
                    tx        <= 1'b0;
                end
            end else begin
                if (clk_count == CLKS_PER_BIT - 1) begin
                    clk_count <= 0;
                    if (bit_index == 4'd9) begin
                        bit_index <= 0;
                        busy      <= 1'b0;
                        tx        <= 1'b1;
                    end else begin
                        bit_index <= bit_index + 1;
                        tx        <= tx_shift[bit_index + 1];
                    end
                end else begin
                    clk_count <= clk_count + 1;
                end
            end
        end
    end
endmodule
