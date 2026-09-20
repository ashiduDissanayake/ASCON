`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 09/20/2026 05:58:19 PM
// Design Name: 
// Module Name: uart_rx
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



// 8N1 UART receiver.
// FPGA clock: 100 MHz
// Default baud: 115200
module uart_rx #(
    parameter integer CLK_FREQ_HZ = 100_000_000,
    parameter integer BAUD_RATE   = 115200
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       rx,
    output reg [7:0]  data_out,
    output reg        data_valid,
    output reg        busy
);

    localparam integer CLKS_PER_BIT = CLK_FREQ_HZ / BAUD_RATE;
    localparam integer HALF_BIT     = CLKS_PER_BIT / 2;

    localparam [2:0] S_IDLE  = 3'd0;
    localparam [2:0] S_START = 3'd1;
    localparam [2:0] S_DATA  = 3'd2;
    localparam [2:0] S_STOP  = 3'd3;

    reg [2:0] state;
    reg [31:0] clk_count;
    reg [2:0] bit_index;
    reg [7:0] rx_shift;

    // Two-flop synchronizer for the asynchronous RX input.
    (* ASYNC_REG = "TRUE" *) reg rx_meta, rx_sync;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rx_meta <= 1'b1;
            rx_sync <= 1'b1;
        end else begin
            rx_meta <= rx;
            rx_sync <= rx_meta;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state      <= S_IDLE;
            clk_count  <= 0;
            bit_index  <= 0;
            rx_shift   <= 0;
            data_out   <= 0;
            data_valid <= 1'b0;
            busy       <= 1'b0;
        end else begin
            data_valid <= 1'b0;

            case (state)
                S_IDLE: begin
                    busy      <= 1'b0;
                    clk_count <= 0;
                    bit_index <= 0;
                    if (!rx_sync) begin
                        busy      <= 1'b1;
                        clk_count <= 0;
                        state     <= S_START;
                    end
                end

                S_START: begin
                    if (clk_count == HALF_BIT - 1) begin
                        clk_count <= 0;
                        if (!rx_sync)
                            state <= S_DATA;
                        else
                            state <= S_IDLE; // false start
                    end else begin
                        clk_count <= clk_count + 1;
                    end
                end

                S_DATA: begin
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count <= 0;
                        rx_shift[bit_index] <= rx_sync;
                        if (bit_index == 3'd7) begin
                            bit_index <= 0;
                            state     <= S_STOP;
                        end else begin
                            bit_index <= bit_index + 1;
                        end
                    end else begin
                        clk_count <= clk_count + 1;
                    end
                end

                S_STOP: begin
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count  <= 0;
                        state      <= S_IDLE;
                        busy       <= 1'b0;
                        // Reject frames whose sampled stop bit is low.
                        if (rx_sync) begin
                            data_out <= rx_shift;
                            data_valid <= 1'b1;
                        end
                    end else begin
                        clk_count <= clk_count + 1;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end
endmodule

