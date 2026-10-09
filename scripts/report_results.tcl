# Called with an implemented design open.
if {![info exists root]} { set root [file normalize [pwd]] }
if {![info exists out]} { set out [file join $root build vivado] }
set reports [file join $out reports]
file mkdir $reports
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose \
  -file [file join $reports timing_summary.rpt]
report_timing -delay_type max -max_paths 20 -path_type full_clock_expanded \
  -file [file join $reports worst_paths.rpt]
report_utilization -hierarchical -file [file join $reports utilization.rpt]
check_timing -verbose -file [file join $reports check_timing.rpt]
report_cdc -details -file [file join $reports cdc.rpt]
report_drc -file [file join $reports drc.rpt]
report_exceptions -file [file join $reports exceptions.rpt]
report_clock_interaction -file [file join $reports clock_interaction.rpt]
set checks [check_timing -verbose -override_defaults {
  no_clock unconstrained_internal_endpoints multiple_clock loops
  partial_input_delay partial_output_delay latch_loops
} -return_string]
foreach {whole count} [regexp -all -inline {There are ([1-9][0-9]*) } $checks] {
  error "incomplete/unsafe timing analysis: $checks"
}
foreach violation [get_drc_violations -quiet] {
  if {[get_property SEVERITY $violation] in {Error {Critical Warning}}} {
    error "blocking DRC: $violation"
  }
}
# report_cdc is written for review. Vivado 2018.1 does not consistently expose
# get_cdc_violations; fail on Critical rows in its portable text format.
set critical_cdc [report_cdc -details -severity Critical -return_string]
if {[regexp {CDC-[0-9]+[[:space:]|]+Critical} $critical_cdc]} {
  error "critical CDC requires repair/review: $critical_cdc"
}
set worst_setup [get_timing_paths -delay_type max -max_paths 1]
set worst_hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $worst_setup] == 0 || [get_property SLACK $worst_setup] < 0} {
  error "post-route setup timing failed or was not analyzed"
}
if {[llength $worst_hold] == 0 || [get_property SLACK $worst_hold] < 0} {
  error "post-route hold timing failed or was not analyzed"
}
write_checkpoint -force [file join $out ascon_gateway_routed.dcp]
write_bitstream -force [file join $out ascon_gateway.bit]
