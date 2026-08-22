#!/usr/bin/env python3
"""
vsc_hdl_tasks.py

One script, four subcommands, driven by the file currently open in VS Code:

  sim       -> compile + run the matching testbench with Icarus Verilog,
               then auto-detect and open whatever VCD file the testbench
               actually dumped (name is read from the simulator's own
               "dumpfile ... opened" message, not assumed).
  waveform  -> just (re)open the most recently modified *.vcd in the repo.
               Useful if you closed GTKWave and want it back without
               re-running the simulation.
  schematic -> generate an SVG schematic for the selected module with yosys
               (reads sources in SystemVerilog mode so casts etc. parse).
  depgraph  -> generate a project-wide dependency graph (HTML) via the
               teroshdl CLI documenter and open it. Falls back to asking
               npm for its global bin dir if the binary isn't on PATH.

Usage (from VS Code tasks.json):
  python3 tools/vsc_hdl_tasks.py sim "${file}"
  python3 tools/vsc_hdl_tasks.py waveform
  python3 tools/vsc_hdl_tasks.py schematic "${file}"
  python3 tools/vsc_hdl_tasks.py depgraph

Conventions assumed:
  <repo>/rtl/<module>.v
  <repo>/tb/<module>_tb.v
  <repo>/tb/tb_common.vh (or other shared includes living in tb/)
  <repo>/build/  (created automatically for schematic/docs output)

Override tool locations with env vars if they're not on PATH:
  ICARUS_BIN   e.g. /Users/you/Tools/oss-cad-suite/bin
  GTKWAVE_BIN  e.g. /Users/you/Tools/oss-cad-suite/bin
  YOSYS_BIN    defaults to "yosys" on PATH
"""

import os
import re
import sys
import glob
import shutil
import subprocess
import platform


def tool_path(env_var, binary_name):
    bin_dir = os.environ.get(env_var, "")
    if bin_dir:
        candidate = os.path.join(bin_dir, binary_name)
        if os.path.exists(candidate):
            return candidate
    return binary_name


def module_name_from_file(path):
    name = os.path.splitext(os.path.basename(path))[0]
    if name.endswith("_tb"):
        name = name[:-3]
    return name


def open_file_cross_platform(path):
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", path])
        elif system == "Windows":
            os.startfile(path)  # type: ignore
        else:
            subprocess.run(["xdg-open", path])
    except Exception as e:
        print(f"ℹ Couldn't auto-open {path} ({e}). Open it manually.")


def run_streaming(cmd, cwd):
    """Run a command, streaming output live AND returning it for parsing."""
    proc = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    lines = []
    for line in proc.stdout:
        print(line, end="")
        lines.append(line)
    proc.wait()
    return proc.returncode, "".join(lines)


def latest_vcd(workspace_root):
    vcds = glob.glob(os.path.join(workspace_root, "**", "*.vcd"), recursive=True)
    if not vcds:
        return None
    return max(vcds, key=os.path.getmtime)


# ---------------------------------------------------------------------------
# sim
# ---------------------------------------------------------------------------
def cmd_sim(workspace_root, selected_file):
    module_name = module_name_from_file(selected_file)
    tb_dir = os.path.join(workspace_root, "tb")
    rtl_dir = os.path.join(workspace_root, "rtl")
    tb_file = os.path.join(tb_dir, f"{module_name}_tb.v")

    if not os.path.isfile(tb_file):
        print(f"❌ No matching testbench found for '{module_name}'.")
        print(f"   Looked for: {tb_file}")
        sys.exit(1)

    rtl_sources = sorted(glob.glob(os.path.join(rtl_dir, "*.v")))
    if not rtl_sources:
        print(f"❌ No RTL sources found in {rtl_dir}")
        sys.exit(1)

    iverilog = tool_path("ICARUS_BIN", "iverilog")
    vvp = tool_path("ICARUS_BIN", "vvp")
    gtkwave = tool_path("GTKWAVE_BIN", "gtkwave")
    sim_out = os.path.join(workspace_root, "sim.vvp")

    print(f"▶ Building testbench for module: {module_name}")
    compile_cmd = [
        iverilog, "-g2012", "-I", tb_dir,
        "-s", f"{module_name}_tb",
        "-o", sim_out,
        tb_file, *rtl_sources,
    ]
    print("  Command   :", " ".join(compile_cmd))
    result = subprocess.run(compile_cmd, cwd=workspace_root)
    if result.returncode != 0:
        print("❌ Compilation failed.")
        sys.exit(result.returncode)

    print("▶ Running simulation...")
    returncode, output = run_streaming([vvp, sim_out], workspace_root)
    if returncode != 0:
        print("❌ Simulation failed.")
        sys.exit(returncode)

    # Figure out which VCD file this testbench actually wrote, by reading
    # the simulator's own "dumpfile X opened for output" message rather
    # than assuming a fixed name — different testbenches in this repo use
    # different $dumpfile names.
    match = re.search(r"dumpfile\s+(\S+)\s+opened", output)
    dump_path = None
    if match:
        dump_name = match.group(1)
        candidate = dump_name if os.path.isabs(dump_name) else os.path.join(workspace_root, dump_name)
        if os.path.isfile(candidate):
            dump_path = candidate

    if not dump_path:
        # Fallback: whatever *.vcd was most recently written
        dump_path = latest_vcd(workspace_root)

    if dump_path:
        print(f"▶ Opening GTKWave with: {dump_path}")
        # start_new_session=True detaches gtkwave from this process's group,
        # so it survives after VS Code closes/reuses the task terminal.
        subprocess.Popen([gtkwave, dump_path], cwd=workspace_root, start_new_session=True)
    else:
        print("ℹ No .vcd found — add $dumpfile/$dumpvars to the testbench for waveforms.")

    print("✅ Done.")


# ---------------------------------------------------------------------------
# waveform (re-open latest, without re-running sim)
# ---------------------------------------------------------------------------
def cmd_waveform(workspace_root):
    gtkwave = tool_path("GTKWAVE_BIN", "gtkwave")
    dump_path = latest_vcd(workspace_root)
    if not dump_path:
        print("❌ No .vcd files found anywhere in the workspace. Run a simulation first.")
        sys.exit(1)
    print(f"▶ Opening most recent waveform: {dump_path}")
    subprocess.Popen([gtkwave, dump_path], cwd=workspace_root, start_new_session=True)


# ---------------------------------------------------------------------------
# schematic
# ---------------------------------------------------------------------------
def cmd_schematic(workspace_root, selected_file):
    module_name = module_name_from_file(selected_file)
    rtl_dir = os.path.join(workspace_root, "rtl")
    build_dir = os.path.join(workspace_root, "build")
    os.makedirs(build_dir, exist_ok=True)

    rtl_sources = sorted(glob.glob(os.path.join(rtl_dir, "*.v")))
    if not rtl_sources:
        print(f"❌ No RTL sources found in {rtl_dir}")
        sys.exit(1)

    yosys = tool_path("YOSYS_BIN", "yosys")
    svg_out = os.path.join(build_dir, f"schematic_{module_name}")
    svg_path = svg_out + ".svg"

    # -sv: some files here use SystemVerilog-only syntax (e.g. cast
    # expressions in ascon_permutation.v) that the plain Verilog-2005
    # frontend rejects. -sv is a superset, safe for plain Verilog too.
    read_cmds = "; ".join(f"read_verilog -sv {f}" for f in rtl_sources)

    netlistsvg_bin = shutil.which("netlistsvg")

    if netlistsvg_bin:
        # Nicer path: emit a JSON netlist and let netlistsvg draw proper
        # gate-symbol schematics (AND/OR/XOR/NOT shapes), closer to what
        # TerosHDL's own viewer produces, instead of raw graphviz boxes.
        json_out = os.path.join(build_dir, f"{module_name}.json")
        yosys_script = (
            f"{read_cmds}; "
            f"hierarchy -top {module_name}; "
            f"proc; opt; "
            f"write_json {json_out}"
        )
        print(f"▶ Generating schematic for module: {module_name} (netlistsvg)")
        result = subprocess.run([yosys, "-p", yosys_script], cwd=workspace_root)
        if result.returncode != 0:
            print("❌ yosys failed to produce the netlist JSON.")
            sys.exit(result.returncode)

        result = subprocess.run([netlistsvg_bin, json_out, "-o", svg_path], cwd=workspace_root)
        if result.returncode != 0 or not os.path.isfile(svg_path):
            print("❌ netlistsvg failed to render the schematic — check output above.")
            sys.exit(1)

        print(f"✅ Schematic written to {svg_path}")
        open_file_cross_platform(svg_path)
        return

    # Fallback: plain yosys `show` via graphviz. Works but renders raw
    # gate-primitive boxes ($xor, $and, ...) rather than proper symbols.
    # `show` can only draw ONE module at a time — if the top module still
    # has a submodule left after synthesis (e.g. ascon_pC -> ascon_round_const),
    # it errors with "only one module must be selected" unless we tell it
    # explicitly which module to draw.
    yosys_script = (
        f"{read_cmds}; "
        f"hierarchy -top {module_name}; "
        f"proc; opt; "
        f"show -format svg -prefix {svg_out} {module_name}"
    )

    print(f"▶ Generating schematic for module: {module_name} (graphviz fallback)")
    print("  ℹ For nicer gate-symbol schematics, install netlistsvg:  npm install -g netlistsvg")
    result = subprocess.run([yosys, "-p", yosys_script], cwd=workspace_root)
    if result.returncode != 0:
        print("❌ yosys failed. If the error mentions 'dot' not found, install graphviz:")
        print("   brew install graphviz")
        sys.exit(result.returncode)

    if os.path.isfile(svg_path):
        print(f"✅ Schematic written to {svg_path}")
        open_file_cross_platform(svg_path)
    else:
        print("❌ Expected SVG not found — check yosys output above for the real error.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# depgraph
# ---------------------------------------------------------------------------
def find_documenter():
    """Locate teroshdl-hdl-documenter even if npm's global bin isn't on PATH."""
    path = shutil.which("teroshdl-hdl-documenter")
    if path:
        return path
    try:
        result = subprocess.run(["npm", "bin", "-g"], capture_output=True, text=True)
        npm_bin = result.stdout.strip()
        if npm_bin:
            candidate = os.path.join(npm_bin, "teroshdl-hdl-documenter")
            if os.path.isfile(candidate):
                return candidate
            print(f"ℹ npm's global bin dir is {npm_bin}, but the binary wasn't found there either.")
    except FileNotFoundError:
        pass
    return None


def cmd_depgraph(workspace_root):
    rtl_dir = os.path.join(workspace_root, "rtl")
    build_dir = os.path.join(workspace_root, "build", "doc")
    os.makedirs(build_dir, exist_ok=True)

    documenter = find_documenter()
    if not documenter:
        print("❌ 'teroshdl-hdl-documenter' not found.")
        print("   Install it first:  npm install -g teroshdl")
        print("   If you've already installed it and this still fails, run:")
        print("     npm bin -g")
        print("   ...and add that directory to your PATH in ~/.zshrc, e.g.:")
        print('     export PATH="$(npm bin -g):$PATH"')
        sys.exit(1)

    cmd = [documenter, "-i", rtl_dir, "-o", "html", "--dep"]
    print("▶ Generating project dependency graph...")
    print("  Command   :", " ".join(cmd))
    result = subprocess.run(cmd, cwd=build_dir)
    if result.returncode != 0:
        print("❌ Documentation generation failed.")
        sys.exit(result.returncode)

    index_html = os.path.join(build_dir, "index.html")
    if os.path.isfile(index_html):
        print(f"✅ Docs (with dependency graph) written to {build_dir}")
        open_file_cross_platform(index_html)
    else:
        print(f"ℹ Command finished but no index.html found in {build_dir} — check output above.")


# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: vsc_hdl_tasks.py <sim|waveform|schematic|depgraph> [selected_file]")
        sys.exit(1)

    action = sys.argv[1]
    workspace_root = os.getcwd()  # tasks.json sets cwd to ${workspaceFolder}
    selected_file = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else None

    if action == "sim":
        if not selected_file:
            print("❌ 'sim' needs the active file path.")
            sys.exit(1)
        cmd_sim(workspace_root, selected_file)
    elif action == "waveform":
        cmd_waveform(workspace_root)
    elif action == "schematic":
        if not selected_file:
            print("❌ 'schematic' needs the active file path.")
            sys.exit(1)
        cmd_schematic(workspace_root, selected_file)
    elif action == "depgraph":
        cmd_depgraph(workspace_root)
    else:
        print(f"❌ Unknown action '{action}'. Use sim, waveform, schematic, or depgraph.")
        sys.exit(1)


if __name__ == "__main__":
    main()