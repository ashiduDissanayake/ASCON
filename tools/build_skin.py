#!/usr/bin/env python3
"""
build_skin.py

Finds the default.svg skin that ships alongside your installed netlistsvg,
merges in extra_cells_skin.svg (symbols for $neg/$add/$sub/$mul/$div/$mod/
$pow/$shl/$shr/$shift/$reduce_*, which the stock skin has no symbol for at
all), and writes the merged result to <repo>/build/skins/digital_extended.svg.

Run this once after installing/updating netlistsvg. Then point
vsc_hdl_tasks.py at the result -- see skin_path() in that file, which
auto-detects build/skins/digital_extended.svg or honors NETLISTSVG_SKIN.

Usage:
  python3 tools/build_skin.py [workspace_root]

If it can't find the skin automatically, set NETLISTSVG_SKIN_SOURCE to
point straight at it and re-run:
  NETLISTSVG_SKIN_SOURCE=/path/to/default.svg python3 tools/build_skin.py
"""

import os
import sys
import glob
import shutil
import subprocess


EXTRA_SKIN_FRAGMENT = "extra_cells_skin.svg"  # sits next to this script


def looks_like_a_skin(path):
    """A real netlistsvg skin defines the component library -- cheapest
    signal is that it has a template for $type="and". (Distinguishes the
    real lib/default.svg from unrelated *.svg files that might share a
    directory, e.g. README screenshots.)"""
    try:
        text = open(path, "r", encoding="utf-8", errors="ignore").read()
    except OSError:
        return False
    return 's:type="and"' in text or "s:type='and'" in text


def find_default_skin():
    """Locate netlistsvg's bundled default.svg. Tries, in order:

    1. NETLISTSVG_SKIN_SOURCE env var, if the user just told us directly.
    2. Relative to the REAL netlistsvg binary on PATH (resolving symlinks --
       this is the one that actually matters, since `npm root -g` can
       report a different prefix than the shell that put netlistsvg on
       PATH, e.g. under nvm/Homebrew. Walking up from the binary itself
       is what `which netlistsvg` + `netlistsvg ...` in cmd_schematic
       already relies on, so it can't be wrong the same way.)
    3. `npm root -g` / local node_modules, as a fallback for conventional
       installs where the above didn't apply.

    Returns (path, tried) -- tried is the list of locations checked, so
    callers can print a useful diagnostic on failure.
    """
    tried = []

    override = os.environ.get("NETLISTSVG_SKIN_SOURCE")
    if override:
        tried.append(override)
        if os.path.isfile(override) and looks_like_a_skin(override):
            return override, tried
        print(f"⚠ NETLISTSVG_SKIN_SOURCE={override} doesn't look like a valid skin file — ignoring it.")

    # --- Walk up from the actual binary netlistsvg resolves to ---
    exe = shutil.which("netlistsvg")
    if exe:
        real_exe = os.path.realpath(exe)  # follow symlinks (npm global installs are usually symlinks)
        start_dir = os.path.dirname(real_exe)
        # Look a few levels up from the binary/script: covers layouts like
        #   .../lib/node_modules/netlistsvg/bin/netlistsvg.js  (want ../lib/default.svg)
        #   .../lib/node_modules/netlistsvg/built/main.js      (want ../lib/default.svg)
        current = start_dir
        for _ in range(5):
            candidates = glob.glob(os.path.join(current, "**", "default.svg"), recursive=True)
            for c in candidates:
                tried.append(c)
                if looks_like_a_skin(c):
                    return c, tried
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    else:
        tried.append("(netlistsvg not found on PATH at all)")

    # --- Conventional npm layouts, as a fallback ---
    local_candidates = glob.glob(os.path.join("node_modules", "netlistsvg", "**", "*.svg"), recursive=True)
    for c in local_candidates:
        tried.append(c)
        if looks_like_a_skin(c):
            return c, tried

    try:
        result = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True)
        global_root = result.stdout.strip()
        if global_root:
            global_candidates = glob.glob(os.path.join(global_root, "netlistsvg", "**", "*.svg"), recursive=True)
            for c in global_candidates:
                tried.append(c)
                if looks_like_a_skin(c):
                    return c, tried
    except FileNotFoundError:
        pass

    return None, tried


def merge(default_skin_path, extra_fragment_path, out_path):
    base = open(default_skin_path, "r", encoding="utf-8").read()
    extra = open(extra_fragment_path, "r", encoding="utf-8").read()

    # Strip the extra fragment's own leading XML comment block so we don't
    # nest comments inside comments -- drop everything up to (and
    # including) the last "-->" before the real <g> defs start.
    marker = "-->"
    idx = extra.rfind(marker)
    extra_body = extra[idx + len(marker):] if idx != -1 else extra

    if "</svg>" not in base:
        raise ValueError(f"{default_skin_path} doesn't look like a well-formed skin (no </svg>)")

    merged = base.replace("</svg>", extra_body + "\n</svg>")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(merged)


def main():
    workspace_root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    default_skin, tried = find_default_skin()
    if not default_skin:
        print("❌ Couldn't find netlistsvg's default.svg skin. Looked in:")
        for t in tried:
            print(f"   - {t}")
        print()
        print("   Find it yourself with:")
        print('     find "$(dirname "$(readlink -f "$(which netlistsvg)" 2>/dev/null || which netlistsvg)")" -name default.svg')
        print("   (on macOS without GNU readlink: node -e \"console.log(require.resolve('netlistsvg/lib/default.svg'))\" may also work)")
        print("   then re-run as:")
        print("     NETLISTSVG_SKIN_SOURCE=/path/you/found/default.svg python3 tools/build_skin.py")
        sys.exit(1)

    extra_fragment = os.path.join(script_dir, EXTRA_SKIN_FRAGMENT)
    if not os.path.isfile(extra_fragment):
        print(f"❌ Expected to find {EXTRA_SKIN_FRAGMENT} next to this script, but it's not there.")
        sys.exit(1)

    out_path = os.path.join(workspace_root, "build", "skins", "digital_extended.svg")
    print(f"▶ Base skin   : {default_skin}")
    print(f"▶ Extra cells : {extra_fragment}")
    merge(default_skin, extra_fragment, out_path)
    print(f"✅ Merged skin written to {out_path}")


if __name__ == "__main__":
    main()