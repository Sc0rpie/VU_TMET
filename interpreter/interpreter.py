#!/usr/bin/env python3
import argparse
import sys
import re
from collections import defaultdict

CHARSETS = {"ANSI_CHARSET", "SYMBOL_CHARSET"}
FLAGS = {"NEED_CONVERTED"}

familydef_re = re.compile(r"^([A-Za-z][\w-]*)\.(\d+)$")
fontcharset_re = re.compile(r"^fontcharset\.([A-Za-z][\w-]*)\.(\d+)$")
exclusion_re = re.compile(r"^exclusion\.([A-Za-z][\w-]*)\.(\d+)$")


def parse_properties(path):
    errors = []
    warnings = []

    # Parsed data structures (with line tracking where useful)
    font_defs = {}  # (family, index) -> {font, charset, needsConverted, line}
    fontcharset = {}  # (family, index) -> {class, line}
    exclusions = defaultdict(list)  # family -> list of {start, end, line}
    globals_ = {"defaultChar": None, "inputTextCharset": None}
    seen_keys = set()

    def err(ln, msg):
        errors.append(f"Line {ln}: {msg}")

    def warn(ln, msg):
        warnings.append(f"Line {ln}: {msg}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = list(enumerate(f, start=1))
    except Exception as e:
        print(f"Error: cannot read file: {e}", file=sys.stderr)
        sys.exit(2)

    for ln, raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        line = evaluate_key_arithmetic(line)

        if "=" not in line:
            err(ln, f"Expected key=value, found: {line}")
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        value = evaluate_arithmetic_value(value)

        if key in seen_keys and not key.startswith("exclusion."):
            # Exact duplicate key (exclusions allow multiple .i entries)
            err(ln, f"Duplicate key: {key}")
        seen_keys.add(key)

        # default.char
        if key == "default.char":
            if not value:
                err(ln, "default.char value is empty")
                continue
            try:
                v = int(value, 10)
            except ValueError:
                err(ln, f"default.char must be an integer, got: {value}")
                continue
            if not (0 <= v <= 0x10FFFF):
                err(ln, f"default.char out of range 0..0x10FFFF: {v}")
                continue
            globals_["defaultChar"] = v
            continue

        # inputtextcharset
        if key == "inputtextcharset":
            if value not in CHARSETS:
                err(ln, f"inputtextcharset must be one of {sorted(CHARSETS)}, got: {value}")
                continue
            globals_["inputTextCharset"] = value
            continue

        # fontcharset.family.index
        m = fontcharset_re.match(key)
        if m:
            family, idx = m.group(1), int(m.group(2))
            if not value:
                err(ln, f"fontcharset.{family}.{idx} has empty class name")
                continue
            fontcharset[(family, idx)] = {"class": value, "line": ln}
            continue

        # exclusion.family.index
        m = exclusion_re.match(key)
        if m:
            family, idx = m.group(1), int(m.group(2))
            if "-" not in value:
                err(ln, f"exclusion range must be start-end hex, got: {value}")
                continue
            s_hex, e_hex = value.split("-", 1)
            s_hex, e_hex = s_hex.strip(), e_hex.strip()
            try:
                s_val = int(s_hex, 16)
                e_val = int(e_hex, 16)
            except ValueError:
                err(ln, f"exclusion range parts must be hex, got: {value}")
                continue
            if not (0 <= s_val <= e_val <= 0xFFFF):
                err(ln, f"exclusion range must satisfy 0x0000 <= start <= end <= 0xFFFF, got: {value}")
                continue
            exclusions[family].append({"start": s_val, "end": e_val, "line": ln})
            continue

        # family.index = FontName,CHARSET[,NEED_CONVERTED]
        m = familydef_re.match(key)
        if m:
            family, idx = m.group(1), int(m.group(2))
            parts = [p.strip() for p in value.split(",") if p.strip() != ""]
            if len(parts) < 2:
                err(ln, f"FontDefinition requires at least FontName,CHARSET; got: {value}")
                continue
            font_name = parts[0]
            charset = parts[1]
            flags = parts[2:] if len(parts) > 2 else []
            for fl in flags:
                if fl not in FLAGS:
                    err(ln, f"Unknown flag '{fl}' in {family}.{idx} (allowed: {sorted(FLAGS)})")
            if charset not in CHARSETS:
                err(ln, f"Unknown charset '{charset}' in {family}.{idx} (allowed: {sorted(CHARSETS)})")
            key2 = (family, idx)
            if key2 in font_defs:
                prev_line = font_defs[key2]["line"]
                err(ln, f"Duplicate FontDefinition for {family}.{idx} (previous at line {prev_line})")
                continue
            needs_converted = "NEED_CONVERTED" in flags
            font_defs[key2] = {
                "family": family,
                "index": idx,
                "font": font_name,
                "charset": charset,
                "needsConverted": needs_converted,
                "line": ln,
            }
            continue

        # Unknown key
        err(ln, f"Unknown key: {key}")

    # Semantic checks
    # 1) Presence of globals
    if globals_["defaultChar"] is None:
        errors.append("Global: default.char is missing")
    if globals_["inputTextCharset"] is None:
        errors.append("Global: inputtextcharset is missing")

    # 2) Family index contiguity and duplicates (dups already handled)
    by_family = defaultdict(list)
    for (fam, idx), rec in font_defs.items():
        by_family[fam].append(idx)
    for fam, idxs in by_family.items():
        if not idxs:
            continue
        s = sorted(set(idxs))
        expected = list(range(s[0], s[-1] + 1))
        if s and s[0] != 0:
            errors.append(f"Family '{fam}': indices must start at 0, found {s[0]}")
        missing = [i for i in expected if i not in s]
        if missing:
            errors.append(f"Family '{fam}': indices not contiguous, missing {missing}")

    # 3) NEED_CONVERTED constraints for SYMBOL_CHARSET
    for (fam, idx), rec in font_defs.items():
        charset = rec["charset"]
        needs = rec["needsConverted"]
        if needs and charset != "SYMBOL_CHARSET":
            errors.append(f"Line {rec['line']}: NEED_CONVERTED used with non-symbol charset in {fam}.{idx}")
        if charset == "SYMBOL_CHARSET" and needs:
            if (fam, idx) not in fontcharset:
                errors.append(
                    f"Line {rec['line']}: Missing fontcharset.{fam}.{idx} for SYMBOL_CHARSET with NEED_CONVERTED"
                )
        if (fam, idx) in fontcharset and not needs and charset == "SYMBOL_CHARSET":
            fc_line = fontcharset[(fam, idx)]["line"]
            warnings.append(f"Line {fc_line}: fontcharset.{fam}.{idx} present but NEED_CONVERTED not set in {fam}.{idx}")

    # 4) Validate fontcharset entries that refer to unknown definitions
    for (fam, idx), fc in fontcharset.items():
        if (fam, idx) not in font_defs:
            warnings.append(f"Line {fc['line']}: fontcharset.{fam}.{idx} has no matching FontDefinition; it will be ignored")

    return font_defs, fontcharset, exclusions, globals_, errors, warnings


def evaluate_key_arithmetic(text):
    def eval_match(match):
        expr = match.group(1)
        try:
            result = eval(expr, {"__builtins__": {}}, {})
            if isinstance(result, (int, float)):
                return str(int(result) if result == int(result) else result)
            return match.group(0)
        except:
            return match.group(0)

    pattern = r"\(([0-9+\-*/.()\s]+)\)"
    return re.sub(pattern, eval_match, text)


def evaluate_arithmetic_value(value):
    # Check if value looks like an arithmetic expression
    if not re.search(r"[+\-*/]", value):
        return value

    # Check if it only contains numbers, operators, spaces, parentheses, and dots (for decimals)
    if not re.match(r"^[0-9+\-*/.()\s]+$", value.strip()):
        return value

    try:
        result = eval(value.strip(), {"__builtins__": {}}, {})
        if isinstance(result, (int, float)):
            return str(int(result) if result == int(result) else result)
    except:
        pass

    return value


def build_normalized(font_defs, fontcharset, exclusions, globals_):
    # families -> {family -> [entries sorted by index]}
    families = {}
    fam_to_entries = defaultdict(list)
    for (fam, idx), rec in font_defs.items():
        fam_to_entries[fam].append(rec)
    for fam, entries in fam_to_entries.items():
        entries_sorted = sorted(entries, key=lambda r: r["index"])
        normalized_list = []
        for r in entries_sorted:
            e = {
                "index": r["index"],
                "font": r["font"],
                "charset": r["charset"],
                "needsConverted": r["needsConverted"],
            }
            if r["charset"] == "SYMBOL_CHARSET":
                cc = fontcharset.get((fam, r["index"]))
                e["converterClass"] = cc["class"] if cc else None
            normalized_list.append(e)
        families[fam] = normalized_list

    # exclusions -> {family -> [ {start, end} ]}
    ex_norm = {}
    for fam, ranges in exclusions.items():
        if not ranges:
            continue
        uniq = []
        seen = set()
        for r in sorted(ranges, key=lambda x: (x["start"], x["end"])):  # sort & dedupe
            key = (r["start"], r["end"])
            if key not in seen:
                seen.add(key)
                uniq.append({"start": r["start"], "end": r["end"]})
        ex_norm[fam] = uniq

    g = {
        "defaultChar": globals_["defaultChar"],
        "inputTextCharset": globals_["inputTextCharset"],
    }

    return families, ex_norm, g


def print_normalized(families, exclusions, globals_):
    def q(s):
        return '"' + s.replace('"', '\\"') + '"'

    print("families:")
    for fam in sorted(families.keys()):
        print(f"  {fam}:")
        for e in families[fam]:
            print(f"    - index: {e['index']}")
            print(f"      font: {q(e['font'])}")
            print(f"      charset: {e['charset']}")
            nc = "true" if e["needsConverted"] else "false"
            print(f"      needsConverted: {nc}")
            if e["charset"] == "SYMBOL_CHARSET":
                cc = e.get("converterClass")
                if cc is None:
                    print(f"      converterClass: null")
                else:
                    print(f"      converterClass: {q(cc)}")

    print()
    print("exclusions:")
    if exclusions:
        for fam in sorted(exclusions.keys()):
            ranges = exclusions[fam]
            parts = []
            for r in ranges:
                s = f"{{ start: 0x{r['start']:04X}, end: 0x{r['end']:04X} }}"
                parts.append(s)
            joined = ", ".join(parts)
            print(f"  {fam}: [{joined}]")

    print()
    print("globals:")
    print(f"  defaultChar: {globals_['defaultChar']}")
    print(f"  inputTextCharset: {globals_['inputTextCharset']}")


# --------------------------
# INTERPRETER (the new part)
# --------------------------
def codepoint_from_arg(s: str) -> int:
    s = s.strip().lower()
    if s.startswith("0x"):
        return int(s, 16)
    if all(c in "0123456789abcdef" for c in s) and len(s) <= 6 and not s.isdigit():
        # Accept bare hex like '03A9'
        return int(s, 16)
    return int(s, 10)

def is_excluded(cp: int, ex_ranges):
    for r in ex_ranges or []:
        if r["start"] <= cp <= r["end"]:
            return True
    return False

def choose_font(families, exclusions, globals_, family: str, codepoint: int, explain=False):
    """
    Simple, deterministic interpretation policy:

    1) If cp lies in family exclusion ranges -> status 'excluded', fallback defaultChar.
    2) Iterate family entries in index order:
       - ANSI_CHARSET covers 0x0000..0x00FF.
       - SYMBOL_CHARSET requires needsConverted==True AND converterClass present to be usable.
         (We don't check actual glyph coverage here; that’s domain-specific.)
       First rule that matches wins.
    3) If nothing matches, return defaultChar fallback.

    You can refine step (2) later by plugging real cmap coverage.
    """
    trace = []
    fam_entries = families.get(family, [])
    ex_ranges = exclusions.get(family)

    if is_excluded(codepoint, ex_ranges):
        msg = {
            "status": "excluded",
            "family": family,
            "codepoint": codepoint,
            "fallbackDefaultChar": globals_["defaultChar"],
            "reason": "codepoint is in family exclusion range"
        }
        return (msg, trace)

    for e in fam_entries:
        cs = e["charset"]
        if cs == "ANSI_CHARSET":
            trace.append(f"Check ANSI {e['font']} (index {e['index']})")
            if codepoint <= 0x00FF:
                return ({
                    "status": "ok",
                    "family": family,
                    "font": e["font"],
                    "charset": cs,
                    "needsConverted": False,
                    "converterClass": None,
                    "codepoint": codepoint
                }, trace)
        elif cs == "SYMBOL_CHARSET":
            trace.append(f"Check SYMBOL {e['font']} (index {e['index']})")
            if e.get("needsConverted") and e.get("converterClass"):
                # Accept as a symbol-mapped choice
                return ({
                    "status": "ok",
                    "family": family,
                    "font": e["font"],
                    "charset": cs,
                    "needsConverted": True,
                    "converterClass": e.get("converterClass"),
                    "codepoint": codepoint
                }, trace)
            else:
                trace.append("  skipped: NEED_CONVERTED or converterClass missing")

    # Nothing matched: default fallback
    return ({
        "status": "fallback",
        "family": family,
        "codepoint": codepoint,
        "fallbackDefaultChar": globals_["defaultChar"],
        "reason": "no matching entry"
    }, trace)


def cmd_normalize(args):
    font_defs, fontcharset, exclusions, globals_, errors, warnings = parse_properties(args.file)
    if errors:
        print("Errors:", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
        sys.exit(1)
    if warnings and not args.no_warn:
        print("Warnings:", file=sys.stderr)
        for w in warnings:
            print(f"- {w}", file=sys.stderr)
    families, ex_norm, g = build_normalized(font_defs, fontcharset, exclusions, globals_)
    print_normalized(families, ex_norm, g)


def cmd_interp(args):
    font_defs, fontcharset, exclusions, globals_, errors, warnings = parse_properties(args.file)
    if errors:
        print("Errors:", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
        sys.exit(1)
    # Warnings don’t block interpretation; show unless suppressed
    if warnings and not args.no_warn:
        for w in warnings:
            print(f"Warning: {w}", file=sys.stderr)

    families, ex_norm, g = build_normalized(font_defs, fontcharset, exclusions, globals_)

    cp = codepoint_from_arg(args.cp)
    result, trace = choose_font(families, ex_norm, g, args.family, cp, explain=args.explain)

    if args.explain:
        print(f"# Trace for {args.family} cp={hex(cp)}")
        for t in trace:
            print("- " + t)
        print()

    # User-friendly output
    if result["status"] == "ok":
        nc = "yes" if result.get("needsConverted") else "no"
        cc = result.get("converterClass")
        print("decision: OK")
        print(f" family: {result['family']}")
        print(f" codepoint: {hex(result['codepoint'])}")
        print(f" font: {result['font']}")
        print(f" charset: {result['charset']}")
        print(f" needsConverted: {nc}")
        if cc:
            print(f" converterClass: {cc}")
    elif result["status"] == "excluded":
        print("decision: EXCLUDED")
        print(f" family: {result['family']}")
        print(f" codepoint: {hex(result['codepoint'])}")
        print(f" reason: {result['reason']}")
        print(f" fallback.defaultChar: {result['fallbackDefaultChar']}")
    else:
        print("decision: FALLBACK")
        print(f" family: {result['family']}")
        print(f" codepoint: {hex(result['codepoint'])}")
        print(f" reason: {result['reason']}")
        print(f" fallback.defaultChar: {result['fallbackDefaultChar']}")


def main():
    ap = argparse.ArgumentParser(description="font.properties semantic normalizer and interpreter")
    sub = ap.add_subparsers(dest="cmd")

    # normalize (default)
    ap_norm = sub.add_parser("normalize", help="Normalize & pretty-print data (default)")
    ap_norm.add_argument("file", help="Path to font.properties")
    ap_norm.add_argument("--no-warn", action="store_true", help="Suppress warnings on stderr")
    ap_norm.set_defaults(func=cmd_normalize)

    # interpreter
    ap_interp = sub.add_parser("interp", help="Interpret: choose a font for a family and codepoint")
    ap_interp.add_argument("file", help="Path to font.properties")
    ap_interp.add_argument("--family", required=True, help="Family name (e.g., dialog, serif)")
    ap_interp.add_argument("--cp", required=True, help="Codepoint (e.g., 0x41, 65, or 03A9)")
    ap_interp.add_argument("--explain", action="store_true", help="Show decision trace")
    ap_interp.add_argument("--no-warn", action="store_true", help="Suppress warnings on stderr")
    ap_interp.set_defaults(func=cmd_interp)

    # If no subcommand, behave like normalize for backward compatibility
    args = ap.parse_args()
    if args.cmd is None:
        # synthesize default subcommand
        class _Args:
            def __init__(self, file, no_warn):
                self.file = file
                self.no_warn = no_warn
        if len(sys.argv) < 2:
            ap.print_help()
            sys.exit(2)
        args2 = _Args(sys.argv[1], False)
        cmd_normalize(args2)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
