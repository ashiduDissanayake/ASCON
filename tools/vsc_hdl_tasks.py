#!/usr/bin/env python3
"""
vsc_hdl_tasks.py

One script, five subcommands, driven by the file currently open in VS Code:

  sim       -> compile + run the matching testbench with Icarus Verilog,
               then auto-detect and open whatever VCD file the testbench
               actually dumped (name is read from the simulator's own
               "dumpfile ... opened" message, not assumed).
  waveform  -> just (re)open the most recently modified *.vcd in the repo.
               Useful if you closed GTKWave and want it back without
               re-running the simulation.
  schematic -> generate an SVG schematic for the selected module with yosys
               (reads sources in SystemVerilog mode so casts etc. parse).
  stats     -> run yosys stat on the selected module and print an area-like
               cell-count summary; useful for UNROLL / area comparisons.
  depgraph  -> generate a project-wide dependency graph (HTML) via the
               teroshdl CLI documenter and open it. Falls back to asking
               npm for its global bin dir if the binary isn't on PATH.

Usage (from VS Code tasks.json):
  python3 tools/vsc_hdl_tasks.py sim "${file}"
  python3 tools/vsc_hdl_tasks.py waveform
  python3 tools/vsc_hdl_tasks.py schematic "${file}"
  python3 tools/vsc_hdl_tasks.py stats "${file}"
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
import json


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


def find_render_target_module(selected_file, module_name, rtl_sources):
    """Return the first child module instantiation we can render. This is used
       for sequential wrappers like ascon_permutation, where netlistsvg crashes
       on cyclic state-feedback graphs but the underlying combinational child
       module still produces a valid, exact schematic netlist.
    """
    try:
        text = open(selected_file, "r", encoding="utf-8").read()
    except OSError:
        return None

    rtl_module_names = {os.path.splitext(os.path.basename(p))[0] for p in rtl_sources}
    seen = set()
    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_$]*)\s+[A-Za-z_][A-Za-z0-9_$]*\s*\(", text):
        candidate = match.group(1)
        if candidate in seen or candidate == module_name:
            continue
        seen.add(candidate)
        if candidate in rtl_module_names:
            return candidate
    return None


def generate_simplified_dot(json_path, dot_path, top_module):
    """Generate a simplified hierarchical DOT from a Yosys write_json output.

    The simplified graph collapses primitive gates and wires, showing only
    module instances, register cells, and top-level ports. This produces a
    readable, high-level netlist for sequential wrappers like ascon_permutation.
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as fh:
            j = json.load(fh)
    except Exception as e:
        print(f"⚠ Could not load JSON netlist {json_path}: {e}")
        return False

    modules = j.get('modules', {})
    if top_module not in modules:
        print(f"⚠ Top module {top_module} not found in JSON.")
        return False

    top = modules[top_module]
    cells = top.get('cells', {})
    ports = top.get('ports', {})

    # Build mapping of bit -> set(nodes) where nodes are cell names or port markers
    bit_to_nodes = {}

    for cname, cell in cells.items():
        conns = cell.get('connections', {})
        for pname, bits in conns.items():
            for b in bits:
                bit_to_nodes.setdefault(b, set()).add(cname)

    for pname, pinfo in ports.items():
        for b in pinfo.get('bits', []):
            bit_to_nodes.setdefault(b, set()).add(f"port__{pname}")

    # Build node labels and detect register-like cells
    module_names = set(modules.keys())
    node_labels = {}
    regs = set()
    for cname, cell in cells.items():
        ctype = cell.get('type', '')
        if ctype in module_names:
            node_labels[cname] = f"{cname}\\n({ctype})"
        else:
            # primitives and regs
            node_labels[cname] = f"{cname}\\n({ctype})"
            if ctype in ("$dff", "$adff", "$adffst", "$dlatch"):
                regs.add(cname)

    for pname in ports.keys():
        node_labels[f"port__{pname}"] = pname

    # Collect edges between nodes that share a net bit
    edges = set()
    for b, nodes in bit_to_nodes.items():
        lst = list(nodes)
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a = lst[i]
                bnode = lst[j]
                key = tuple(sorted((a, bnode)))
                edges.add(key)

    # Emit DOT
    try:
        with open(dot_path, 'w', encoding='utf-8') as fh:
            fh.write(f'digraph "{top_module}_simplified" {{\n')
            fh.write('  rankdir=LR; splines=ortho; nodesep=0.6; ranksep=0.8;\n')
            fh.write('  node [shape=box,fontname="Arial",fontsize=10];\n')

            for nid, lbl in node_labels.items():
                shape = 'doublecircle' if nid in regs else 'box'
                fh.write(f'  "{nid}" [label="{lbl}", shape={shape}];\n')

            for a, bnode in sorted(edges):
                fh.write(f'  "{a}" -> "{bnode}" [dir=both, arrowhead=none, arrowtail=none, color="#666666"];\n')

            fh.write('}\n')
    except Exception as e:
        print(f"⚠ Could not write DOT file {dot_path}: {e}")
        return False

    return True


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
# stats
# ---------------------------------------------------------------------------
def cmd_stats(workspace_root, selected_file):
    module_name = module_name_from_file(selected_file)
    rtl_dir = os.path.join(workspace_root, "rtl")
    yosys = tool_path("YOSYS_BIN", "yosys")
    rtl_sources = sorted(glob.glob(os.path.join(rtl_dir, "*.v")))
    if not rtl_sources:
        print(f"❌ No RTL sources found in {rtl_dir}")
        sys.exit(1)

    read_cmds = "; ".join(f"read_verilog -sv {f}" for f in rtl_sources)
    yosys_script = (
        f"{read_cmds}; "
        f"hierarchy -top {module_name}; "
        f"proc; opt; stat"
    )
    print(f"▶ Running yosys stat for module: {module_name}")
    print("  Command   :", yosys, "-p", yosys_script)
    result = subprocess.run([yosys, "-p", yosys_script], cwd=workspace_root)
    if result.returncode != 0:
        print("❌ yosys stat failed. If your environment lacks Yosys, install it and retry.")
        sys.exit(result.returncode)


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

    # Exact sequential-netlist schematic rendering path:
    # - netlistsvg is a DAG renderer and crashes on feedback loops in
    #   ascon_permutation (state_reg -> ascon_round -> state_reg)
    # - Yosys' native `show -format dot` keeps the hierarchy and lets Graphviz
    #   render the cyclic structure correctly without recursion overflow.
    dot_path = os.path.join(build_dir, f"schematic_{module_name}.dot")
    dot_bin = shutil.which("dot")
    if not dot_bin:
        print("❌ Graphviz 'dot' not found. Install it first:")
        print("   brew install graphviz")
        sys.exit(1)

    yosys_script = (
        f"{read_cmds}; "
        f"hierarchy -top {module_name}; "
        f"proc; opt_clean; "
        f"show -format dot -prefix {svg_out} {module_name}"
    )

    print(f"▶ Generating exact schematic for module: {module_name} (Yosys + Graphviz)")
    print("  ℹ netlistsvg fails on feedback-heavy sequential graphs; this direct dot pipeline is the correct renderer for the true top-level netlist.")
    result = subprocess.run([yosys, "-p", yosys_script], cwd=workspace_root)
    if result.returncode != 0:
        print("❌ Yosys failed to generate the DOT view for the schematic.")
        sys.exit(result.returncode)

    if not os.path.isfile(dot_path):
        print(f"❌ Expected DOT file not found: {dot_path}")
        sys.exit(1)

    result = subprocess.run([dot_bin, "-Tsvg", dot_path, "-o", svg_path], cwd=workspace_root)
    if result.returncode != 0 or not os.path.isfile(svg_path):
        print("❌ Graphviz failed to render the DOT schematic to SVG.")
        sys.exit(1)

    print(f"✅ Exact schematic written to {svg_path}")

    # Also create a simplified high-level DOT from the Yosys JSON and render it.
    # This collapses primitive gates into module/regs/ports nodes for readability.
    json_out = os.path.join(build_dir, f"{module_name}.json")
    simp_dot = os.path.join(build_dir, f"schematic_{module_name}_simplified.dot")
    simp_svg = os.path.join(build_dir, f"schematic_{module_name}_simplified.svg")

    print(f"▶ Producing simplified hierarchical schematic for: {module_name}")
    json_script = f"{read_cmds}; hierarchy -top {module_name}; proc; opt; write_json {json_out}"
    result = subprocess.run([yosys, "-p", json_script], cwd=workspace_root)
    if result.returncode == 0 and os.path.isfile(json_out):
        ok = generate_simplified_dot(json_out, simp_dot, module_name)
        if ok:
            result = subprocess.run([dot_bin, "-Tsvg", simp_dot, "-o", simp_svg], cwd=workspace_root)
            if result.returncode == 0 and os.path.isfile(simp_svg):
                print(f"✅ Simplified schematic written to {simp_svg}")
            else:
                print("⚠ Failed to render simplified DOT via Graphviz.")
        else:
            print("⚠ Failed to generate simplified DOT from Yosys JSON.")
    else:
        print("⚠ Failed to ask Yosys to emit JSON for simplified schematic.")

    # Also keep the previous 'clean submodule' path if available
    child_module = find_render_target_module(selected_file, module_name, rtl_sources)
    if child_module and child_module != module_name and netlistsvg_bin:
        clean_svg = os.path.join(build_dir, f"schematic_{child_module}_clean.svg")
        clean_json = os.path.join(build_dir, f"{child_module}_clean.json")
        clean_script = (
            f"{read_cmds}; "
            f"hierarchy -top {child_module}; "
            f"proc; opt; "
            f"write_json {clean_json}"
        )
        print(f"ℹ Also generating a clean DAG render for submodule: {child_module}")
        result = subprocess.run([yosys, "-p", clean_script], cwd=workspace_root)
        if result.returncode == 0:
            result = subprocess.run([netlistsvg_bin, clean_json, "-o", clean_svg], cwd=workspace_root)
            if result.returncode == 0 and os.path.isfile(clean_svg):
                print(f"✅ Clean submodule schematic written to {clean_svg}")

    open_file_cross_platform(svg_path)
    return


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
        print("Usage: vsc_hdl_tasks.py <sim|waveform|schematic|stats|depgraph> [selected_file]")
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
    elif action == "stats":
        if not selected_file:
            print("❌ 'stats' needs the active file path.")
            sys.exit(1)
        cmd_stats(workspace_root, selected_file)
    elif action == "depgraph":
        cmd_depgraph(workspace_root)
    else:
        print(f"❌ Unknown action '{action}'. Use sim, waveform, schematic, stats, or depgraph.")
        sys.exit(1)


if __name__ == "__main__":
    main()