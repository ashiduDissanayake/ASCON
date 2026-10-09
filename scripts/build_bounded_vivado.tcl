# vivado -mode batch -source scripts/build_bounded_vivado.tcl
# Optional -tclargs C:/path/to/ASCON for Windows redirected paths.
set bounded_root [expr {$argc > 0 ? [lindex $argv 0] : [pwd]}]
set argv [list $bounded_root ascon_basys3_bounded_top]
set argc 2
source [file join $bounded_root scripts build_vivado.tcl]
