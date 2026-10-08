# Called with an implemented design open.
if {![info exists root]} { set root [file normalize [pwd]] }
set reports [file join $root build vivado reports]
file mkdir $reports
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose \
  -file [file join $reports timing_summary.rpt]
report_timing -delay_type max -max_paths 20 -path_type full_clock_expanded \
  -file [file join $reports worst_paths.rpt]
report_utilization -hierarchical -file [file join $reports utilization.rpt]
check_timing -verbose -file [file join $reports check_timing.rpt]
report_cdc -details -file [file join $reports cdc.rpt]
report_drc -file [file join $reports drc.rpt]
set worst_setup [get_timing_paths -delay_type max -max_paths 1]
set worst_hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $worst_setup] == 0 || [get_property SLACK $worst_setup] < 0} {
  error "post-route setup timing failed or was not analyzed"
}
if {[llength $worst_hold] == 0 || [get_property SLACK $worst_hold] < 0} {
  error "post-route hold timing failed or was not analyzed"
}
write_checkpoint -force [file join $root build vivado ascon_gateway_routed.dcp]
write_bitstream -force [file join $root build vivado ascon_gateway.bit]
