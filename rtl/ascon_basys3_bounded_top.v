`timescale 1ns/1ps
module ascon_basys3_bounded_top #(
    parameter integer CLK_FREQ_HZ=100_000_000,
    parameter integer BAUD_RATE=115200,
    parameter integer RX_TIMEOUT_CYCLES=CLK_FREQ_HZ/10
)(input wire CLK100MHZ,btnC,RsRx,output wire RsTx,output wire [3:0] led);
    (* ASYNC_REG="TRUE" *) reg [1:0] reset_sync;
    always @(posedge CLK100MHZ or posedge btnC)
        if(btnC)reset_sync<=0;else reset_sync<={reset_sync[0],1'b1};
    wire rst_n=reset_sync[1];
    wire [7:0] rx_data,tx_data;
    wire rx_valid,rx_busy,tx_valid,tx_busy,execution_busy,execution_done;
    uart_rx #(.CLK_FREQ_HZ(CLK_FREQ_HZ),.BAUD_RATE(BAUD_RATE)) u_uart_rx(
        .clk(CLK100MHZ),.rst_n(rst_n),.rx(RsRx),.data_out(rx_data),.data_valid(rx_valid),.busy(rx_busy));
    uart_tx #(.CLK_FREQ_HZ(CLK_FREQ_HZ),.BAUD_RATE(BAUD_RATE)) u_uart_tx(
        .clk(CLK100MHZ),.rst_n(rst_n),.data_in(tx_data),.data_valid(tx_valid),.tx(RsTx),.busy(tx_busy));
    ascon_uart_buffered_protocol #(.CLK_FREQ_HZ(CLK_FREQ_HZ),.RX_TIMEOUT_CYCLES(RX_TIMEOUT_CYCLES)) u_protocol(
        .clk(CLK100MHZ),.rst_n(rst_n),.rx_data(rx_data),.rx_valid(rx_valid),
        .tx_data(tx_data),.tx_valid(tx_valid),.tx_busy(tx_busy),
        .execution_busy(execution_busy),.execution_done(execution_done));
    assign led={execution_done,execution_busy,tx_busy,rx_busy};
endmodule
