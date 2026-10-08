# Reproducible Basys 3 implementation. Run from the repository root:
# vivado -mode batch -source scripts/build_vivado.tcl
# Vivado 2018.1 may misresolve redirected Desktop paths. If so, append:
# -tclargs C:/absolute/path/to/ASCON (a short 8.3 path is also accepted).
set root [expr {$argc > 0 ? [lindex $argv 0] : [pwd]}]
puts "Repository root: $root"
cd $root
set out [file join $root build vivado]
file mkdir $out
set metadata [open [file join $out build_metadata.txt] w]
puts $metadata "vivado=[version -short]"
puts $metadata "commit=[exec git -C $root rev-parse HEAD]"
puts $metadata "dirty=[expr {[exec git -C $root status --porcelain] ne ""}]"
puts $metadata "part=xc7a35tcpg236-1"
puts $metadata "top=ascon_basys3_top"
puts $metadata "clock_hz=100000000"
puts $metadata "strategy=synth_design,opt_design,place_design,phys_opt_design,route_design"
close $metadata
create_project -force ascon_gateway $out -part xc7a35tcpg236-1
add_files [glob [file join $root rtl *.v]]
add_files -fileset constrs_1 [file join $root constraints basys3_master.xdc]
set_property top ascon_basys3_top [current_fileset]
update_compile_order -fileset sources_1
read_xdc [file join $root constraints basys3_master.xdc]
synth_design -top ascon_basys3_top -part xc7a35tcpg236-1
opt_design
place_design
phys_opt_design
route_design
source [file join $root scripts report_results.tcl]
