#!/usr/bin/env python3
"""Read an Azure DevOps backlog export (CSV or XLSX) into normalised JSON.

Standard library only - no package installs needed.

Usage:
    python read_backlog.py <export.csv|export.xlsx> [--out backlog.json] [--process process.json]

Writes backlog.json (input for build_outputs.py) and prints:
  1. an indented outline of the hierarchy (ID [Type] Title (State))
  2. quality findings (missing content, vague titles, invalid states, bad parents)
"""
import argparse
import csv
import html
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"

DEFAULT_PROCESS = {
    "types": {
        "Epic": {"states": ["New", "In Progress", "Done", "Removed"], "remove_state": "Removed",
                 "allowed_parents": [], "requires_acceptance_criteria": True, "allows_acceptance_criteria": True},
        "Feature": {"states": ["New", "In Progress", "Done", "Removed"], "remove_state": "Removed",
                    "allowed_parents": ["Epic"], "requires_acceptance_criteria": True, "allows_acceptance_criteria": True},
        "Product Backlog Item": {"states": ["New", "Approved", "Committed", "Done", "Removed"], "remove_state": "Removed",
                                 "allowed_parents": ["Feature"], "requires_acceptance_criteria": True,
                                 "allows_acceptance_criteria": True},
        "Bug": {"states": ["New", "Approved", "Committed", "Done", "Removed"], "remove_state": "Removed",
                "allowed_parents": ["Feature"], "requires_acceptance_criteria": False, "allows_acceptance_criteria": True},
        "Task": {"states": ["To Do", "In Progress", "Done", "Removed"], "remove_state": "Removed",
                 "allowed_parents": ["Product Backlog Item", "Bug"], "requires_acceptance_criteria": False,
                 "allows_acceptance_criteria": False},
        "Impediment": {"states": ["Open", "Closed"], "remove_state": "Closed",
                       "allowed_parents": ["Epic", "Feature", "Product Backlog Item", "Bug", None],
                       "requires_acceptance_criteria": False, "allows_acceptance_criteria": False},
        "Risk": {"states": ["Proposed", "Active", "Resolved", "Closed"], "remove_state": "Closed",
                 "allowed_parents": ["Epic", "Feature", "Product Backlog Item", None],
                 "requires_acceptance_criteria": False, "allows_acceptance_criteria": False},
    },
    "title_warn_length": 80,
}
CLOSED_STATES = {"Done", "Removed", "Closed"}
VAGUE_WORDS = {"stuff", "things", "misc", "tbd", "todo", "etc", "various", "general", "work", "fix", "update"}
RECOMMENDED_COLUMNS = ["State", "Area Path", "Iteration Path", "Description", "Acceptance Criteria"]


def load_process(path=None):
    candidates = [Path(path)] if path else [Path(__file__).resolve().parent.parent / "references" / "process.json"]
    for c in candidates:
        if c.is_file():
            with open(c, encoding="utf-8") as f:
                return json.load(f)
    return DEFAULT_PROCESS


# ---------------------------------------------------------------- file readers
def _col_index(ref):
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_xlsx(path):
    """Return the first worksheet as a list of rows (lists of strings)."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.iter(M + "si"):
                shared.append("".join(t.text or "" for t in si.iter(M + "t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        first = wb.find(M + "sheets").find(M + "sheet")
        rid = first.get(R + "id")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels.iter(PR + "Relationship") if r.get("Id") == rid)
        target = target.lstrip("/")
        sheet_path = target if target.startswith("xl/") else "xl/" + target
        sheet = ET.fromstring(z.read(sheet_path))
        rows = []
        for row in sheet.iter(M + "row"):
            vals = {}
            for c in row.iter(M + "c"):
                idx = _col_index(c.get("r"))
                t = c.get("t")
                if t == "s":
                    v = c.find(M + "v")
                    val = shared[int(v.text)] if v is not None else ""
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(M + "t"))
                else:
                    v = c.find(M + "v")
                    val = v.text if v is not None and v.text is not None else ""
                    if re.fullmatch(r"-?\d+\.0", val):
                        val = val[:-2]
                vals[idx] = val
            if vals:
                width = max(vals) + 1
                rows.append([vals.get(i, "") for i in range(width)])
            else:
                rows.append([])
        return rows


def read_csv(path):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=enc) as f:
                return list(csv.reader(f))
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"ERROR: could not decode {path} as UTF-8 or Windows-1252")


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"(?i)<li[^>]*>", "\n• ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


# ---------------------------------------------------------------- normalise
def normalise(rows, source):
    hdr_i = next((i for i, r in enumerate(rows) if any(c.strip().lower() == "work item type" for c in r)), None)
    if hdr_i is None:
        raise SystemExit("ERROR: no header row with 'Work Item Type' found. Export from an Azure DevOps query.")
    header = [c.strip() for c in rows[hdr_i]]
    lower = {h.lower(): i for i, h in enumerate(header)}
    if "id" not in lower:
        raise SystemExit("ERROR: export has no ID column. Add ID to the query columns and re-export.")

    title_cols = []
    for i, h in enumerate(header):
        m = re.fullmatch(r"title(?: (\d+))?", h.lower())
        if m:
            title_cols.append((int(m.group(1) or 1), i))
    title_cols.sort()
    if not title_cols:
        raise SystemExit("ERROR: no Title column found.")
    tree_export = any(h.lower().startswith("title ") for h in header)
    parent_i = lower.get("parent")

    field_cols = [h for i, h in enumerate(header)
                  if h and i not in {ix for _, ix in title_cols} and i != parent_i]

    items, stack, issues = [], {}, []
    for n, r in enumerate(rows[hdr_i + 1:]):
        r = r + [""] * (len(header) - len(r))
        if not any(c.strip() for c in r):
            continue
        raw_id = r[lower["id"]].strip()
        if not raw_id.isdigit():
            issues.append({"id": None, "severity": "warning", "code": "NO_ID",
                           "message": f"Row {hdr_i + n + 2} has no numeric ID and was skipped."})
            continue
        wid = int(raw_id)
        depth, title = None, ""
        for lvl, ix in title_cols:
            if r[ix].strip():
                depth, title = lvl, r[ix].strip()
                break
        parent = None
        if parent_i is not None and r[parent_i].strip().isdigit():
            parent = int(r[parent_i].strip())
        elif tree_export and depth:
            stack[depth] = wid
            for d in list(stack):
                if d > depth:
                    del stack[d]
            parent = stack.get(depth - 1)
        if tree_export and depth:
            stack[depth] = wid
        fields = {h: r[header.index(h)] for h in field_cols}
        items.append({"id": wid, "type": fields.get("Work Item Type", "").strip(), "title": title,
                      "state": fields.get("State", "").strip(), "parent": parent, "order": len(items),
                      "fields": fields})
    return header, field_cols, len(title_cols), items, issues


def compute_depths(items):
    by_id = {i["id"]: i for i in items}
    for it in items:
        d, p, seen = 1, it["parent"], set()
        while p in by_id and p not in seen:
            seen.add(p)
            d += 1
            p = by_id[p]["parent"]
        it["depth"] = d


def quality_checks(items, columns, process):
    types = process["types"]
    by_id = {i["id"]: i for i in items}
    issues = []
    warn_len = process.get("title_warn_length", 80)
    has_desc, has_ac = "Description" in columns, "Acceptance Criteria" in columns
    seen_titles = {}

    def add(it, sev, code, msg):
        issues.append({"id": it["id"], "severity": sev, "code": code, "message": msg})

    for it in items:
        t, cfg = it["type"], types.get(it["type"])
        if cfg is None:
            add(it, "error", "UNKNOWN_TYPE", f"Type '{t}' is not in process.json.")
            continue
        if it["state"] and it["state"] not in cfg["states"]:
            add(it, "error", "INVALID_STATE", f"State '{it['state']}' is not valid for {t} ({', '.join(cfg['states'])}).")
        if it["parent"] is not None:
            p = by_id.get(it["parent"])
            if p is None:
                add(it, "info", "PARENT_NOT_IN_EXPORT", f"Parent {it['parent']} is not in this export.")
            elif cfg["allowed_parents"] and p["type"] not in cfg["allowed_parents"]:
                add(it, "warning", "BAD_PARENT", f"{t} sits under {p['type']} {p['id']}; expected {', '.join(x for x in cfg['allowed_parents'] if x)}.")
            elif not cfg["allowed_parents"]:
                add(it, "warning", "BAD_PARENT", f"{t} should be top level but sits under {p['id']}.")
        elif cfg["allowed_parents"] and None not in cfg["allowed_parents"]:
            add(it, "warning", "ORPHAN", f"{t} has no parent; expected under {', '.join(x for x in cfg['allowed_parents'] if x)}.")

        if it["state"] in CLOSED_STATES:
            continue  # content checks only for open work
        words = re.findall(r"[A-Za-z0-9']+", it["title"])
        if len(it["title"]) > warn_len:
            add(it, "warning", "TITLE_TOO_LONG", f"Title is {len(it['title'])} chars; keep under {warn_len}.")
        if len(words) < 3 or any(w.lower() in VAGUE_WORDS for w in words):
            add(it, "warning", "VAGUE_TITLE", f"Title '{it['title']}' is vague; use verb + subject.")
        key = (t, it["title"].lower())
        if key in seen_titles:
            add(it, "warning", "DUPLICATE_TITLE", f"Same title as {seen_titles[key]}.")
        seen_titles.setdefault(key, it["id"])
        desc = strip_html(it["fields"].get("Description", "")) if has_desc else None
        if has_desc and not desc:
            add(it, "warning", "MISSING_DESCRIPTION", "No description / story statement.")
        elif has_desc and "so that" not in desc.lower():
            add(it, "info", "NOT_STORY_FORMAT", "Description has no 'so that' clause (System/Job Story format).")
        elif has_desc and t in ("Epic", "Feature", "Product Backlog Item") and len(desc) < 25:
            add(it, "warning", "THIN_DESCRIPTION", "Description too thin to act on.")
        ac = strip_html(it["fields"].get("Acceptance Criteria", "")) if has_ac else ""
        if has_ac and cfg.get("requires_acceptance_criteria") and not ac:
            add(it, "warning", "MISSING_AC", "No acceptance criteria.")
        if has_ac and not cfg.get("allows_acceptance_criteria") and ac:
            add(it, "info", "UNEXPECTED_AC", f"{t} has acceptance criteria; standard says none.")
    return issues


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export")
    ap.add_argument("--out", default="backlog.json")
    ap.add_argument("--process")
    a = ap.parse_args()

    path = Path(a.export)
    rows = read_xlsx(path) if path.suffix.lower() in (".xlsx", ".xlsm") else read_csv(path)
    header, columns, title_levels, items, issues = normalise(rows, path.name)
    compute_depths(items)
    process = load_process(a.process)
    issues += quality_checks(items, columns, process)
    missing = [c for c in RECOMMENDED_COLUMNS if c not in columns]

    out = {"source_file": path.name, "columns": columns, "title_levels": title_levels,
           "has_parent_column": "parent" in {h.lower() for h in header},
           "missing_recommended_columns": missing, "items": items, "issues": issues}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print(f"Read {len(items)} work items from {path.name} -> {a.out}")
    if missing:
        print("WARNING: export is missing recommended columns: " + ", ".join(missing))
    print("\nOUTLINE")
    children = {}
    ids = {i["id"] for i in items}
    for it in items:
        children.setdefault(it["parent"] if it["parent"] in ids else None, []).append(it)

    def walk(pid, lvl):
        for it in children.get(pid, []):
            print(f"{'  ' * lvl}{it['id']} [{it['type']}] {it['title']} ({it['state']})")
            walk(it["id"], lvl + 1)
    walk(None, 0)

    if issues:
        print(f"\nQUALITY FINDINGS ({len(issues)})")
        for i in sorted(issues, key=lambda x: ({"error": 0, "warning": 1, "info": 2}[x["severity"]], x["id"] or 0)):
            print(f"  {i['severity'].upper():7} {i['id'] or '-':>6} {i['code']}: {i['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
