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

# ---------------------------------------------------------------------------
# Friendly names / shapes / colors for Yosys' internal RTLIL cell types.
# Anything not in this table falls back to its raw $type name so nothing
# silently goes unlabeled — it just won't look as pretty until you add it
# here.
#
#   key             -> (friendly_label, shape,      fillcolor)
# ---------------------------------------------------------------------------
CELL_FRIENDLY = {
    # arithmetic
    "$add":         ("+",          "box",      "#dff0d8"),
    "$sub":         ("\u2212",     "box",      "#dff0d8"),
    "$mul":         ("\u00d7",     "box",      "#dff0d8"),
    "$div":         ("\u00f7",     "box",      "#dff0d8"),
    "$mod":         ("mod",        "box",      "#dff0d8"),
    "$neg":         ("neg",        "box",      "#dff0d8"),
    "$pos":         ("+ (unary)",  "box",      "#dff0d8"),

    # comparators
    "$eq":          ("==",         "box",      "#fcf3cf"),
    "$ne":          ("!=",         "box",      "#fcf3cf"),
    "$eqx":         ("=== ",       "box",      "#fcf3cf"),
    "$nex":         ("!==",        "box",      "#fcf3cf"),
    "$gt":          (">",          "box",      "#fcf3cf"),
    "$ge":          (">=",         "box",      "#fcf3cf"),
    "$lt":          ("<",          "box",      "#fcf3cf"),
    "$le":          ("<=",         "box",      "#fcf3cf"),

    # bitwise / word-level logic
    "$and":         ("AND",        "box",      "#d6eaf8"),
    "$or":          ("OR",         "box",      "#d6eaf8"),
    "$xor":         ("XOR",        "box",      "#d6eaf8"),
    "$xnor":        ("XNOR",       "box",      "#d6eaf8"),
    "$not":         ("NOT",        "box",      "#d6eaf8"),
    "$logic_and":   ("&&",         "box",      "#d6eaf8"),
    "$logic_or":    ("||",         "box",      "#d6eaf8"),
    "$logic_not":   ("!",          "box",      "#d6eaf8"),
    "$reduce_and":  ("&-reduce",   "box",      "#d6eaf8"),
    "$reduce_or":   ("|-reduce",   "box",      "#d6eaf8"),
    "$reduce_xor":  ("^-reduce",   "box",      "#d6eaf8"),
    "$reduce_xnor": ("^~-reduce",  "box",      "#d6eaf8"),
    "$reduce_bool": ("nonzero?",   "box",      "#d6eaf8"),

    # shifts
    "$shl":         ("<<",         "box",      "#ebdef0"),
    "$shr":         (">>",         "box",      "#ebdef0"),
    "$sshl":        ("<<< ",       "box",      "#ebdef0"),
    "$sshr":        (">>> ",       "box",      "#ebdef0"),
    "$shift":       ("shift",      "box",      "#ebdef0"),
    "$shiftx":      ("shift (x)",  "box",      "#ebdef0"),

    # muxes / selection
    "$mux":         ("MUX",        "diamond",  "#fadbd8"),
    "$pmux":        ("MUX (pri.)", "diamond",  "#fadbd8"),
    "$demux":       ("DEMUX",      "diamond",  "#fadbd8"),
    "$procmux":     ("MUX",        "diamond",  "#fadbd8"),

    # registers / storage (drawn with a register-style box)
    "$dff":         ("REG",        "box3d",    "#d5f5e3"),
    "$dffe":        ("REG (en)",   "box3d",    "#d5f5e3"),
    "$adff":        ("REG (arst)", "box3d",    "#d5f5e3"),
    "$adffe":       ("REG (arst,en)", "box3d", "#d5f5e3"),
    "$sdff":        ("REG (srst)", "box3d",    "#d5f5e3"),
    "$sdffe":       ("REG (srst,en)", "box3d", "#d5f5e3"),
    "$aldff":       ("REG (aload)", "box3d",   "#d5f5e3"),
    "$dlatch":      ("LATCH",      "box3d",    "#d5f5e3"),
    "$ff":          ("REG",        "box3d",    "#d5f5e3"),
    "$procdff":     ("REG",        "box3d",    "#d5f5e3"),

    # constants / misc
    "$const":       ("const",      "box",      "#eaeded"),
}

# Cell types (or type-prefixes) that represent storage — used to draw the
# register/latch double-bordered symbol even for internal auto-generated
# names like `$procdff$226` or `$auto$ff.cc:337:slice$238`.
_REG_TYPES = {
    "$dff", "$dffe", "$adff", "$adffe", "$sdff", "$sdffe",
    "$aldff", "$dlatch", "$ff", "$procdff", "$opt_dff",
}


_SRC_CELL_RE = re.compile(r'([^/\\]+\.s?v):(\d+)\$(\d+)$')


def _short_cell_id(cname):
    """Shorten a Yosys cell name for display.

    Cells derived straight from source (e.g.
    '$add$/Users/you/rtl/ascon_permutation.v:39$156') carry the full
    absolute file path, which makes labels huge. Collapse that down to
    just 'ascon_permutation.v:39 #156'. Pass-generated names like
    '$procdff$216' or '$auto$ff.cc:337:slice$238' are already short and
    are returned unchanged.
    """
    m = _SRC_CELL_RE.search(cname)
    if m:
        return f"{m.group(1)}:{m.group(2)} #{m.group(3)}"
    return cname


def _friendly_cell_label(cname, ctype):
    """Return (label, shape, fillcolor) for a cell, given its instance name
    and Yosys $type. Falls back gracefully for unknown/auto-generated types."""
    short_id = _short_cell_id(cname)

    if ctype in CELL_FRIENDLY:
        friendly, shape, color = CELL_FRIENDLY[ctype]
        return f"{friendly}\n{short_id}", shape, color

    # Auto-generated helper cells (e.g. "$auto$ff.cc:337:slice$238") don't
    # have a clean $type match above, but often *are* a $dff/$adffe etc.
    # under the hood — check the raw type again for a known register kind
    # even if the outer match above missed a variant.
    if ctype in _REG_TYPES or ctype.startswith("$adff") or ctype.startswith("$dff") or ctype.startswith("$sdff"):
        return f"REG\n{short_id}", "box3d", "#d5f5e3"

    if cname.startswith("$auto$"):
        # Internal Yosys-generated helper (slice/join/etc.), not something
        # from your RTL — label it plainly as such rather than a raw path.
        return f"(internal helper)\n{ctype}", "box", "#f5f5f5"

    # Unknown/unmapped cell type: show the raw type so it's still
    # informative, just not yet given a friendly name in CELL_FRIENDLY.
    return f"{short_id}\n({ctype})", "box", "#ffffff"


def generate_simplified_dot(json_path, dot_path, top_module):
    """Generate a simplified hierarchical DOT from a Yosys write_json output.

    The simplified graph collapses primitive gates and wires, showing only
    module instances, register cells, and top-level ports. This produces a
    readable, high-level netlist for sequential wrappers like ascon_permutation.

    Cells are given friendly labels/shapes/colors from CELL_FRIENDLY instead
    of raw Yosys $type strings, and are grouped into clusters (registers /
    control-mux / datapath-arith / submodule instances / ports) so the
    layout reads more like an actual schematic.
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

    # Build node labels/shapes/colors and bucket cells into clusters
    module_names = set(modules.keys())
    node_labels = {}
    node_shapes = {}
    node_colors = {}
    regs = set()
    clusters = {
        "registers": [],
        "control_mux": [],
        "datapath": [],
        "instances": [],
        "other": [],
    }

    for cname, cell in cells.items():
        ctype = cell.get('type', '')

        if ctype in module_names:
            # Submodule instance (e.g. an ascon_round instance) — keep this
            # as its own box naming both the instance and the module type.
            node_labels[cname] = f"{cname}\n[{ctype} instance]"
            node_shapes[cname] = "component"
            node_colors[cname] = "#d4e6f1"
            clusters["instances"].append(cname)
            continue

        label, shape, color = _friendly_cell_label(cname, ctype)
        node_labels[cname] = label
        node_shapes[cname] = shape
        node_colors[cname] = color

        if shape == "box3d" or ctype in _REG_TYPES:
            regs.add(cname)
            clusters["registers"].append(cname)
        elif shape == "diamond":
            clusters["control_mux"].append(cname)
        elif ctype.startswith("$auto$"):
            clusters["other"].append(cname)
        else:
            clusters["datapath"].append(cname)

    for pname in ports.keys():
        node_labels[f"port__{pname}"] = pname
        node_shapes[f"port__{pname}"] = "oval"
        node_colors[f"port__{pname}"] = "#ffffff"

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

    cluster_titles = {
        "registers": "Registers",
        "control_mux": "Control / Muxes",
        "datapath": "Datapath (arith / logic)",
        "instances": "Submodule instances",
        "other": "Internal helpers",
    }

    # Emit DOT
    try:
        with open(dot_path, 'w', encoding='utf-8') as fh:
            fh.write(f'digraph "{top_module}_simplified" {{\n')
            fh.write('  rankdir=LR; splines=ortho; nodesep=0.5; ranksep=0.9;\n')
            fh.write('  node [fontname="Arial",fontsize=10,style=filled];\n')
            fh.write('  edge [color="#666666"];\n')

            for cluster_key, members in clusters.items():
                if not members:
                    continue
                fh.write(f'  subgraph cluster_{cluster_key} {{\n')
                fh.write(f'    label="{cluster_titles[cluster_key]}";\n')
                fh.write('    style=dashed; color="#aaaaaa"; fontname="Arial"; fontsize=11;\n')
                for nid in members:
                    lbl = node_labels[nid]
                    shape = node_shapes.get(nid, "box")
                    color = node_colors.get(nid, "#ffffff")
                    fh.write(f'    "{nid}" [label="{lbl}", shape={shape}, fillcolor="{color}"];\n')
                fh.write('  }\n')

            # Ports live outside any cluster
            for pname in ports.keys():
                nid = f"port__{pname}"
                fh.write(f'  "{nid}" [label="{node_labels[nid]}", shape=oval, fillcolor="#ffffff"];\n')

            for a, bnode in sorted(edges):
                fh.write(f'  "{a}" -> "{bnode}" [dir=both, arrowhead=none, arrowtail=none];\n')

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
    dot_bin = shutil.which("dot")

    # ------------------------------------------------------------------
    # Exact schematic: try netlistsvg FIRST (this is the renderer that
    # actually draws proper gate/mux/dff symbols with clean routing —
    # it's what makes ascon_pS / ascon_round look good).
    #
    # netlistsvg's DAG layout only chokes on sequential feedback
    # (state_reg -> ascon_round -> state_reg) when the JSON still
    # contains raw $adff (async-reset) cells, whose cycle-breaking
    # semantics its dagre-based layout doesn't always resolve cleanly.
    # `techmap -map +/adff2dff.v` rewrites each $adff into a plain
    # $dff fed by a reset $mux, both of which netlistsvg draws
    # natively and which correctly breaks the cycle for layout.
    #
    # NOTE: this techmap'd netlist is ONLY used for the schematic
    # picture. It is never written back to rtl/, never used by the
    # simulation task, and never touched by synthesis — it's a
    # throwaway JSON purely for rendering.
    # ------------------------------------------------------------------
    exact_json = os.path.join(build_dir, f"{module_name}_exact.json")
    netlistsvg_ok = False

    if netlistsvg_bin:
        print(f"▶ Generating exact schematic for module: {module_name} (netlistsvg)")
        exact_script = (
            f"{read_cmds}; "
            f"hierarchy -top {module_name}; "
            f"proc; "
            f"techmap -map +/adff2dff.v; "
            f"opt; "
            f"write_json {exact_json}"
        )
        result = subprocess.run([yosys, "-p", exact_script], cwd=workspace_root)
        if result.returncode == 0 and os.path.isfile(exact_json):
            result = subprocess.run(
                [netlistsvg_bin, exact_json, "-o", svg_path], cwd=workspace_root
            )
            if result.returncode == 0 and os.path.isfile(svg_path):
                netlistsvg_ok = True
                print(f"✅ Exact schematic written to {svg_path}")
            else:
                print("⚠ netlistsvg failed to render this module (likely an "
                      "unsupported cell/topology) — falling back to Graphviz.")
        else:
            print("⚠ Yosys failed to produce JSON for netlistsvg — falling back to Graphviz.")
    else:
        print("ℹ netlistsvg not found on PATH — using Graphviz for the exact schematic.")

    if not netlistsvg_ok:
        # ------------------------------------------------------------
        # Fallback: Yosys' native `show -format dot` + Graphviz.
        # Keeps the hierarchy and can render cyclic/odd structures that
        # netlistsvg can't, at the cost of a much uglier layout.
        # ------------------------------------------------------------
        if not dot_bin:
            print("❌ Graphviz 'dot' not found. Install it first:")
            print("   brew install graphviz")
            sys.exit(1)

        dot_path = os.path.join(build_dir, f"schematic_{module_name}.dot")
        yosys_script = (
            f"{read_cmds}; "
            f"hierarchy -top {module_name}; "
            f"proc; opt_clean; "
            f"show -format dot -prefix {svg_out} {module_name}"
        )

        print(f"▶ Generating exact schematic for module: {module_name} (Yosys + Graphviz fallback)")
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
            if dot_bin:
                result = subprocess.run([dot_bin, "-Tsvg", simp_dot, "-o", simp_svg], cwd=workspace_root)
                if result.returncode == 0 and os.path.isfile(simp_svg):
                    print(f"✅ Simplified schematic written to {simp_svg}")
                else:
                    print("⚠ Failed to render simplified DOT via Graphviz.")
            else:
                print("⚠ Graphviz 'dot' not found — skipping simplified schematic render.")
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