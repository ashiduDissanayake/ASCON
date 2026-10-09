# Read AFTER synthesis, only for ascon_basys3_bounded_top.
# 100 ps input jitter is a declared implementation budget, not a measured
# oscillator specification. Board qualification must confirm this envelope.
set_input_jitter [get_clocks sys_clk_pin] 0.100

# UART RX is asynchronous. Exclude only the input-to-first-stage path;
# the rx_meta -> rx_sync path remains timed and ASYNC_REG constrains placement.
set rx_first [get_pins -quiet {u_uart_rx/rx_meta_reg/D}]
if {[llength $rx_first] != 1} { error "RX synchronizer endpoint did not resolve" }
set_false_path -from [get_ports RsRx] -to $rx_first

# Button assertion is asynchronous; release is synchronized in reset_sync.
# The synchronized reset distribution inside the design remains timed.
set reset_async [get_pins -quiet {reset_sync_reg[0]/CLR reset_sync_reg[1]/CLR}]
if {[llength $reset_async] != 2} { error "reset synchronizer endpoints did not resolve" }
set_false_path -from [get_ports btnC] -to $reset_async

# UART TX has no phase relationship with the host clock. Bound the local
# register-to-pin propagation to 5 ns; serial-pin tests cover bit cadence.
set_max_delay -datapath_only 5.000 -to [get_ports RsTx]
set_min_delay 0.000 -to [get_ports RsTx]
# LEDs are visual indicators without an external sampling-clock contract.
set_false_path -to [get_ports {led[*]}]
