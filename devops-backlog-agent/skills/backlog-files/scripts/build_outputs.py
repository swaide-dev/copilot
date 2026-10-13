#!/usr/bin/env python3
"""Turn a change set (JSON) into an Azure DevOps CSV import file and a colour-coded Excel preview.

Standard library only - no package installs needed.

Usage:
    python build_outputs.py --changes changes.json [--backlog backlog.json] [--outdir output] [--name prefix]

  --backlog   backlog.json from read_backlog.py. Omit only when creating a brand-new backlog.
  --changes   change set written by the agent (see references/changeset-schema.md).

Outputs (in --outdir):
  <name>_devops_import.csv      upload via Boards > Queries > Import work items
  <name>_preview.xlsx           colour-coded preview + change log + legend

Exit code 1 with a list of ERRORS if the change set breaks a rule. Nothing is written in that case.
Hard rules enforced:
  * never delete - only "new", "update" and "remove" actions exist; "remove" sets the type's remove state
  * every update and remove needs a History note
  * new items get no State (Azure DevOps always imports them as New)
  * parent types must follow the process hierarchy; parents must exist in the backlog or the change set
  * Epic, Feature and Product Backlog Item need acceptance criteria; Task must not have any
  * every column written for existing items must exist in the export, so no existing field is blanked
"""
import argparse
import csv
import datetime as dt
import html
import json
import re
import sys
import zipfile
from pathlib import Path

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
    "field_map": {"description": "Description", "acceptance_criteria": "Acceptance Criteria",
                  "repro_steps": "Repro Steps", "area_path": "Area Path", "iteration_path": "Iteration Path",
                  "tags": "Tags", "priority": "Priority", "effort": "Effort", "assigned_to": "Assigned To"},
    "html_fields": ["Description", "Acceptance Criteria", "Repro Steps"],
    "title_warn_length": 80,
    "max_rows_per_csv": 1000,
}


def load_process(path=None):
    p = Path(path) if path else Path(__file__).resolve().parent.parent / "references" / "process.json"
    if p.is_file():
        with open(p, encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_PROCESS.items():
            cfg.setdefault(k, v)
        return cfg
    return DEFAULT_PROCESS


# ---------------------------------------------------------------- text helpers
HTML_RE = re.compile(r"<(div|p|ul|ol|li|br|b|strong|em|i|span|h\d)\b", re.I)


def to_html(value):
    """Plain text / list -> simple HTML for Azure DevOps rich-text fields. Existing HTML is kept."""
    if value is None:
        return ""
    if isinstance(value, list):
        items = [str(v).strip() for v in value if str(v).strip()]
        return "<ul>" + "".join(f"<li>{html.escape(v, quote=False)}</li>" for v in items) + "</ul>" if items else ""
    s = str(value).strip()
    if not s or HTML_RE.search(s):
        return s
    out, bullets, tag = [], [], "ul"

    def flush():
        if bullets:
            out.append(f"<{tag}>" + "".join(f"<li>{html.escape(b, quote=False)}</li>" for b in bullets) + f"</{tag}>")
            bullets.clear()

    for line in s.splitlines():
        line = line.strip()
        m = re.match(r"^([-*•]|\d+[.)])\s+(.*)", line)
        if m:
            new_tag = "ol" if m.group(1)[0].isdigit() else "ul"
            if bullets and new_tag != tag:
                flush()
            tag = new_tag
            bullets.append(m.group(2))
            continue
        flush()
        if line:
            out.append(f"<p>{html.escape(line, quote=False)}</p>")
    flush()
    return "".join(out)


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"(?i)<li[^>]*>", "\n• ", str(s))
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


# ---------------------------------------------------------------- minimal XLSX writer
def _col(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


_BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# style ids
S_DEFAULT, S_HEADER, S_NEW, S_UPD, S_UPD_CELL, S_REMOVED, S_CONTEXT, S_PLAIN, S_H1, S_BOLD = range(10)
STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="7">
<font><sz val="10"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><sz val="10"/><color rgb="FF006100"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><color rgb="FF000000"/><name val="Calibri"/></font>
<font><sz val="10"/><color rgb="FF7F7F7F"/><name val="Calibri"/></font>
<font><b/><sz val="14"/><name val="Calibri"/></font>
<font><sz val="10"/><color rgb="FF000000"/><name val="Calibri"/></font>
</fonts>
<fills count="8">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F3864"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFC6EFCE"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFEB9C"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFC000"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFF0000"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF2F2F2"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFBFBFBF"/></left><right style="thin"><color rgb="FFBFBFBF"/></right><top style="thin"><color rgb="FFBFBFBF"/></top><bottom style="thin"><color rgb="FFBFBFBF"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="10">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="6" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="3" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="4" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="5" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


class Sheet:
    def __init__(self, name):
        self.name = name[:31]
        self.rows = []          # list of list of (value, style)
        self.widths = {}
        self.freeze = False
        self.autofilter = False

    def add(self, values, styles=S_PLAIN):
        if isinstance(styles, int):
            styles = [styles] * len(values)
        self.rows.append(list(zip(values, styles)))

    def xml(self):
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
               '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>']
        if self.freeze:
            out.append('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
                       'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>')
        if self.widths:
            out.append("<cols>" + "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>'
                                          for i, w in sorted(self.widths.items())) + "</cols>")
        out.append("<sheetData>")
        for r, row in enumerate(self.rows, 1):
            cells = []
            for c, (v, s) in enumerate(row):
                ref = f"{_col(c)}{r}"
                if v is None or v == "":
                    cells.append(f'<c r="{ref}" s="{s}"/>')
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    cells.append(f'<c r="{ref}" s="{s}"><v>{v}</v></c>')
                else:
                    t = _BAD_XML.sub("", str(v))[:32000]
                    cells.append(f'<c r="{ref}" s="{s}" t="inlineStr"><is><t xml:space="preserve">'
                                 f'{html.escape(t, quote=False)}</t></is></c>')
            out.append(f'<row r="{r}">' + "".join(cells) + "</row>")
        out.append("</sheetData>")
        if self.autofilter and self.rows:
            out.append(f'<autoFilter ref="A1:{_col(len(self.rows[0]) - 1)}{len(self.rows)}"/>')
        out.append('<pageMargins left="0.4" right="0.4" top="0.5" bottom="0.5" header="0.3" footer="0.3"/>')
        out.append('<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>')
        out.append("</worksheet>")
        return "\n".join(out)


def write_xlsx(path, sheets):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for i in range(1, len(sheets) + 1)) + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   "</Relationships>")
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{html.escape(s.name)}" sheetId="{i}" r:id="rId{i}"/>'
                             for i, s in enumerate(sheets, 1))
                   + "</sheets>"
                   + ("<definedNames>" + "".join(
                       f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
                       f"'{s.name}'!$A$1:${_col(len(s.rows[0]) - 1)}${len(s.rows)}</definedName>"
                       for i, s in enumerate(sheets) if s.autofilter and s.rows) + "</definedNames>"
                      if any(s.autofilter for s in sheets) else "")
                   + "</workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                             for i in range(1, len(sheets) + 1))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   "</Relationships>")
        z.writestr("xl/styles.xml", STYLES_XML)
        for i, s in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", s.xml())


# ---------------------------------------------------------------- change set processing
class Problems:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")


FRIENDLY = {"state": "State", "title": "Title", "history": "History"}


def norm_fields(ch, field_map):
    """Collect field changes from friendly keys and the explicit 'fields' dict."""
    out = {}
    for k, v in (ch.get("fields") or {}).items():
        out[field_map.get(k.lower(), FRIENDLY.get(k.lower(), k))] = v
    for k, col in list(field_map.items()) + [("state", "State"), ("title", "Title")]:
        if k in ch and ch[k] not in (None, ""):
            out[col] = ch[k]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--changes", required=True)
    ap.add_argument("--backlog")
    ap.add_argument("--outdir", default="output")
    ap.add_argument("--name")
    ap.add_argument("--process")
    a = ap.parse_args()

    proc = load_process(a.process)
    types, fmap = proc["types"], proc["field_map"]
    html_fields = set(proc["html_fields"])
    with open(a.changes, encoding="utf-8") as f:
        cs = json.load(f)
    meta = cs.get("meta", {})
    changes = cs.get("changes", [])
    P = Problems()

    backlog = None
    if a.backlog:
        with open(a.backlog, encoding="utf-8") as f:
            backlog = json.load(f)
    existing = {i["id"]: i for i in backlog["items"]} if backlog else {}
    order = {i["id"]: i["order"] for i in existing.values()}
    export_cols = list(backlog["columns"]) if backlog else []

    if not changes:
        P.err("changes", "change set is empty")

    # ---- pass 1: index new refs
    new_by_ref = {}
    for n, ch in enumerate(changes):
        if ch.get("action") == "new":
            ref = str(ch.get("ref") or f"N{n + 1}")
            ch["ref"] = ref
            if ref in new_by_ref:
                P.err(f"new {ref}", "duplicate ref")
            new_by_ref[ref] = ch

    def ptype(parent):
        if parent is None:
            return None
        if isinstance(parent, int) or (isinstance(parent, str) and parent.isdigit()):
            it = existing.get(int(parent))
            return it["type"] if it else "?missing"
        ch = new_by_ref.get(str(parent))
        return ch.get("type") if ch else "?missing"

    touched = {}   # id -> {"kind": "updated"/"removed", "fields": {...}, "history":..., change}
    news = []
    used_cols = set()

    for n, ch in enumerate(changes):
        act = ch.get("action")
        if act not in ("new", "update", "remove"):
            P.err(f"change #{n + 1}", f"action '{act}' not allowed (only new, update, remove). Work items are never deleted.")
            continue

        if act == "new":
            where = f"new {ch['ref']}"
            t = ch.get("type")
            cfg = types.get(t)
            if not cfg:
                P.err(where, f"unknown type '{t}'. Allowed: {', '.join(types)}")
                continue
            title = (ch.get("title") or "").strip()
            if not title:
                P.err(where, "title is required")
            elif len(title) > 255:
                P.err(where, "title over 255 characters")
            elif len(title) > proc.get("title_warn_length", 80):
                P.warn(where, f"title is {len(title)} chars - KISS, aim for under {proc.get('title_warn_length', 80)}")
            if ch.get("state") or (ch.get("fields") or {}).get("State"):
                P.err(where, "new items can't have a State - Azure DevOps imports them as New. Remove 'state'.")
            parent = ch.get("parent")
            if isinstance(parent, str) and parent.isdigit():
                parent = int(parent)
                ch["parent"] = parent
            pt = ptype(parent)
            if pt == "?missing":
                P.err(where, f"parent {parent} not found in the backlog export or change set")
            elif pt is None:
                if None not in cfg["allowed_parents"] and cfg["allowed_parents"]:
                    P.warn(where, f"{t} has no parent (normally under {'/'.join(x for x in cfg['allowed_parents'] if x)})")
            elif pt not in cfg["allowed_parents"]:
                P.err(where, f"{t} can't sit under {pt}. Allowed parents: {', '.join(str(x) for x in cfg['allowed_parents']) or 'none (top level)'}")
            if parent == ch["ref"]:
                P.err(where, "item can't be its own parent")
            ac = ch.get("acceptance_criteria")
            if cfg.get("requires_acceptance_criteria") and not ac:
                P.err(where, f"{t} needs acceptance criteria")
            if ac and not cfg.get("allows_acceptance_criteria"):
                P.err(where, f"{t} must not have acceptance criteria")
            if isinstance(ac, list) and len(ac) > 6:
                P.warn(where, f"{len(ac)} acceptance criteria - KISS, aim for 2-5")
            if not ch.get("description"):
                P.warn(where, "no description (story statement)")
            if backlog and not ch.get("justification"):
                P.err(where, "justification is required for new items when updating an existing backlog")
            if ch.get("repro_steps") and t != "Bug":
                P.warn(where, "repro_steps only apply to Bugs - ignored")
            news.append(ch)
            continue

        # update / remove
        wid = ch.get("id")
        where = f"{act} {wid}"
        try:
            wid = int(wid)
        except (TypeError, ValueError):
            P.err(where, "id must be an existing work item ID")
            continue
        it = existing.get(wid)
        if not it:
            P.err(where, "ID not found in the backlog export" if backlog else "updates need --backlog")
            continue
        if wid in touched:
            P.err(where, "same ID changed twice - merge into one change")
            continue
        cfg = types.get(it["type"], {})
        hist = (ch.get("history") or "").strip()
        if not hist:
            P.err(where, "History note is required for every update and removal")
        if ch.get("parent") is not None:
            P.err(where, "re-parenting isn't supported via CSV import - move it on the board")
        fields = norm_fields(ch, fmap)
        fields.pop("History", None)
        if act == "remove":
            rs = cfg.get("remove_state", "Removed")
            if it["state"] == rs:
                P.err(where, f"already {rs}")
            fields = {"State": rs}
            kind = "removed"
        else:
            kind = "updated"
            if fields.get("State") == "Removed":
                kind = "removed"
        if "State" in fields:
            if "State" not in export_cols:
                P.err(where, "State column isn't in the export - add it to the query and re-export")
            elif fields["State"] not in cfg.get("states", []):
                P.err(where, f"state '{fields['State']}' not valid for {it['type']} ({', '.join(cfg.get('states', []))})")
            elif fields["State"] == it["state"] and act == "update":
                P.warn(where, f"state is already {it['state']} - no state change")
                fields.pop("State")
        if "Acceptance Criteria" in fields and not cfg.get("allows_acceptance_criteria", True) and fields["Acceptance Criteria"]:
            P.err(where, f"{it['type']} must not have acceptance criteria")
        for col in fields:
            if col != "Title" and col not in export_cols:
                P.err(where, f"column '{col}' isn't in the export - add it to the query and re-export")
        touched[wid] = {"kind": kind, "fields": fields, "history": hist, "change": ch}

    # ---- output columns
    if backlog:
        cols = [c for c in export_cols if c not in ("ID", "Work Item Type", "History")]
        for ch in news:
            t = ch.get("type")
            for key, col in fmap.items():
                if ch.get(key) not in (None, "", []) and not (key == "repro_steps" and t != "Bug"):
                    if col not in cols:
                        if col == "Repro Steps":
                            P.warn(f"new {ch['ref']}", "Repro Steps column not in export - repro steps folded into Description")
                        elif col in ("Area Path", "Iteration Path"):
                            pass
                        else:
                            P.err(f"new {ch['ref']}", f"column '{col}' isn't in the export - add it to the query and re-export")
            for col in (ch.get("fields") or {}):
                if col not in cols and col != "State":
                    P.err(f"new {ch['ref']}", f"column '{col}' isn't in the export - add it to the query and re-export")
    else:
        cols = ["Area Path", "Iteration Path", "Description", "Acceptance Criteria"]
        if any(ch.get("type") == "Bug" and ch.get("repro_steps") for ch in news):
            cols.append("Repro Steps")
        if any(ch.get("tags") for ch in news):
            cols.append("Tags")
        for ch in news:
            for col in (ch.get("fields") or {}):
                if col not in cols:
                    cols.append(col)

    if P.errors:
        print(f"ERRORS ({len(P.errors)}) - nothing written. Fix the change set and re-run:")
        for e in P.errors:
            print("  - " + e)
        if P.warnings:
            print(f"WARNINGS ({len(P.warnings)}):")
            for w in P.warnings:
                print("  - " + w)
        return 1

    # ---- build tree of rows: touched + new + all ancestors (context anchors)
    def key_parent(k):
        if isinstance(k, int):
            p = existing[k]["parent"]
            return p if p in existing else None
        p = new_by_ref[k].get("parent")
        if p is None:
            return None
        return int(p) if (isinstance(p, int) or str(p).isdigit()) else str(p)

    nodes = set()
    for k in list(touched) + [ch["ref"] for ch in news]:
        cur = k
        while cur is not None and cur not in nodes:
            nodes.add(cur)
            cur = key_parent(cur)

    for k in nodes:
        if isinstance(k, int) and existing[k]["parent"] is not None and existing[k]["parent"] not in existing:
            P.warn(f"item {k}", f"its parent {existing[k]['parent']} isn't in the export; it is placed at top level in the CSV")

    news_order = {ch["ref"]: n for n, ch in enumerate(news)}

    def sort_key(k):
        return (0, order[k]) if isinstance(k, int) else (1, news_order[k])

    kids = {}
    for k in nodes:
        kids.setdefault(key_parent(k), []).append(k)
    for v in kids.values():
        v.sort(key=sort_key)

    seq = []  # (key, depth)

    def walk(pk, d):
        for k in kids.get(pk, []):
            seq.append((k, d))
            walk(k, d + 1)
    walk(None, 1)
    levels = max((d for _, d in seq), default=1)
    title_cols = [f"Title {i}" for i in range(1, levels + 1)]

    lead = (["ID"] if backlog else []) + ["Work Item Type"] + title_cols
    if not backlog:
        cols = [c for c in cols if c != "State"]
    out_cols = lead + cols + ["History"]

    # resolve inherited area/iteration for new items
    def inherited(k, col):
        while k is not None:
            if isinstance(k, int):
                return existing[k]["fields"].get(col, "")
            ch = new_by_ref[k]
            v = ch.get(next((key for key, c in fmap.items() if c == col), ""), "") or (ch.get("fields") or {}).get(col, "")
            if v:
                return v
            k = key_parent(k)
        return ""

    rows = []   # dict: values, kind, changed(set), key
    for k, d in seq:
        vals = {c: "" for c in out_cols}
        changed = set()
        if isinstance(k, int):
            it = existing[k]
            for c in cols:
                vals[c] = it["fields"].get(c, "")
            vals["ID"] = k
            vals["Work Item Type"] = it["type"]
            vals[f"Title {d}"] = it["title"]
            if k in touched:
                tc = touched[k]
                kind = tc["kind"]
                for col, v in tc["fields"].items():
                    newv = to_html(v) if col in html_fields else ("; ".join(v) if isinstance(v, list) else str(v))
                    if col == "Title":
                        if newv != it["title"]:
                            vals[f"Title {d}"] = newv
                            changed.add(f"Title {d}")
                        continue
                    if newv != it["fields"].get(col, ""):
                        vals[col] = newv
                        changed.add(col)
                vals["History"] = tc["history"]
                changed.add("History")
            else:
                kind = "context"
        else:
            ch = new_by_ref[k]
            kind = "new"
            vals["Work Item Type"] = ch["type"]
            vals[f"Title {d}"] = ch["title"].strip()
            desc = to_html(ch.get("description"))
            if ch.get("repro_steps") and ch["type"] == "Bug":
                if "Repro Steps" in cols:
                    vals["Repro Steps"] = to_html(ch["repro_steps"])
                else:
                    desc += "<p><b>Repro steps</b></p>" + to_html(ch["repro_steps"])
            if "Description" in cols:
                vals["Description"] = desc
            if "Acceptance Criteria" in cols and ch.get("acceptance_criteria"):
                vals["Acceptance Criteria"] = to_html(ch["acceptance_criteria"])
            for key, col in fmap.items():
                if col in cols and key not in ("description", "acceptance_criteria", "repro_steps") and ch.get(key):
                    vals[col] = to_html(ch[key]) if col in html_fields else str(ch[key])
            for col, v in (ch.get("fields") or {}).items():
                if col in cols:
                    vals[col] = to_html(v) if col in html_fields else str(v)
            for col in ("Area Path", "Iteration Path"):
                if col in cols and not vals[col]:
                    vals[col] = inherited(key_parent(k), col)
            if "State" in vals:
                vals["State"] = ""
            vals["History"] = (ch.get("history") or "").strip()
            changed = set(out_cols)
        rows.append({"key": k, "depth": d, "vals": vals, "kind": kind, "changed": changed})

    # ---- split into CSV files by top-level subtree
    limit = int(proc.get("max_rows_per_csv", 1000))
    groups, cur = [], []
    for r in rows:
        if r["depth"] == 1 and cur:
            groups.append(cur)
            cur = []
        cur.append(r)
    if cur:
        groups.append(cur)
    files, chunk = [], []
    for g in groups:
        if len(g) > limit:
            print(f"ERROR: one top-level subtree has {len(g)} rows (> {limit}). Split the change set.")
            return 1
        if len(chunk) + len(g) > limit:
            files.append(chunk)
            chunk = []
        chunk += g
    if chunk:
        files.append(chunk)

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = dt.date.today().isoformat()
    proj = re.sub(r"[^A-Za-z0-9]+", "-", meta.get("project", "backlog")).strip("-") or "backlog"
    name = a.name or f"{proj}_{stamp}"
    csv_paths = []
    for n, chunk in enumerate(files, 1):
        p = outdir / (f"{name}_devops_import.csv" if len(files) == 1 else f"{name}_devops_import_part{n}.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, quoting=csv.QUOTE_ALL)
            w.writerow(out_cols)
            for r in chunk:
                w.writerow(["" if r["vals"][c] is None else r["vals"][c] for c in out_cols])
        csv_paths.append(p)

    # ---- preview workbook
    label = {"new": "NEW", "updated": "UPDATED", "removed": "REMOVED", "context": "CONTEXT"}
    row_style = {"new": S_NEW, "updated": S_UPD, "removed": S_REMOVED, "context": S_CONTEXT}
    prev = Sheet("Upload preview")
    prev.freeze = prev.autofilter = True
    prev.add(["Change"] + out_cols, S_HEADER)
    for r in rows:
        base = row_style[r["kind"]]
        styles = [base]
        vals = [label[r["kind"]]]
        for c in out_cols:
            v = r["vals"][c]
            vals.append(strip_html(v) if c in html_fields else v)
            styles.append(S_UPD_CELL if (r["kind"] == "updated" and c in r["changed"]) else base)
        prev.add(vals, styles)
    width = {"Change": 11, "ID": 8, "Work Item Type": 18, "Description": 55, "Acceptance Criteria": 45,
             "Repro Steps": 40, "History": 45, "Area Path": 26, "Iteration Path": 26, "State": 12}
    for i, c in enumerate(["Change"] + out_cols):
        prev.widths[i] = width.get(c, 34 if c.startswith("Title") else 18)

    log = Sheet("Change log")
    log.freeze = log.autofilter = True
    log.add(["#", "Change", "ID / Ref", "Type", "Title", "Parent", "Field", "Old value", "New value",
             "History", "Justification", "Source"], S_HEADER)
    n = 0
    for r in rows:
        if r["kind"] == "context":
            continue
        k = r["key"]
        st = row_style[r["kind"]]
        if r["kind"] == "new":
            ch = new_by_ref[k]
            par = ch.get("parent")
            ptitle = (existing[int(par)]["title"] if isinstance(par, int) or str(par).isdigit()
                      else new_by_ref[str(par)]["title"]) if par is not None else "(top level)"
            n += 1
            log.add([n, "NEW", k, ch["type"], ch["title"], f"{par} - {ptitle}" if par is not None else ptitle,
                     "(new item)", "", strip_html(r["vals"].get("Description", "")),
                     r["vals"]["History"], ch.get("justification", ""), ch.get("source", "")], st)
        else:
            it, tc = existing[k], touched[k]
            fields_changed = [c for c in r["changed"] if c != "History"] or ["History only"]
            for c in fields_changed:
                n += 1
                if c == "History only":
                    old, new = "", ""
                elif c.startswith("Title"):
                    old, new = it["title"], r["vals"][c]
                else:
                    old, new = it["fields"].get(c, ""), r["vals"][c]
                    if c in html_fields:
                        old, new = strip_html(old), strip_html(new)
                log.add([n, label[r["kind"]], k, it["type"], it["title"], it["parent"] or "(top level)",
                         c, old, new, tc["history"], tc["change"].get("justification", ""),
                         tc["change"].get("source", "")], st)
    for i, w in enumerate([5, 10, 9, 18, 34, 24, 18, 30, 30, 40, 40, 40]):
        log.widths[i] = w

    counts = {k: sum(1 for r in rows if r["kind"] == k) for k in label}
    leg = Sheet("Legend")
    leg.widths = {0: 22, 1: 90}
    leg.add([f"{meta.get('project', 'Backlog')} - DevOps import preview", ""], [S_H1, S_DEFAULT])
    leg.add(["Source", meta.get("source", "")], [S_BOLD, S_DEFAULT])
    leg.add(["Generated", stamp], [S_BOLD, S_DEFAULT])
    leg.add(["CSV file(s)", ", ".join(p.name for p in csv_paths)], [S_BOLD, S_DEFAULT])
    leg.add(["", ""], S_DEFAULT)
    leg.add(["Colour", "Meaning"], S_HEADER)
    leg.add([f"NEW ({counts['new']})", "New work item. Imports in its initial state (New / To Do / Open / Proposed)."], [S_NEW, S_PLAIN])
    leg.add([f"UPDATED ({counts['updated']})", "Existing item changed. Orange cells are the changed fields; History adds a Discussion comment."], [S_UPD, S_PLAIN])
    leg.add(["Changed cell", "The field value that will change on import."], [S_UPD_CELL, S_PLAIN])
    leg.add([f"REMOVED ({counts['removed']})", "Existing item set to its Removed/Closed state. Never deleted. Reason recorded in History."], [S_REMOVED, S_PLAIN])
    leg.add([f"CONTEXT ({counts['context']})", "Unchanged parent row. Carries the hierarchy (Title 1/2/3...) so new children link to the right parent."], [S_CONTEXT, S_PLAIN])
    leg.add(["", ""], S_DEFAULT)
    leg.add(["Import steps", ""], S_HEADER)
    for i, step in enumerate([
        "Azure DevOps > Boards > Queries > Import work items > choose the CSV > Import.",
        "Check the results grid: changed items show in bold, errors in red. Fix any red rows before saving.",
        "Select Save items.",
        "New items always import as New. To set another state, export them, change State and re-import.",
        "Parent links come from Title column indentation. Context rows must stay in the file."], 1):
        leg.add([f"Step {i}", step], [S_BOLD, S_PLAIN])
    if P.warnings:
        leg.add(["", ""], S_DEFAULT)
        leg.add(["Warnings", ""], S_HEADER)
        for wmsg in P.warnings:
            leg.add(["", wmsg], [S_DEFAULT, S_PLAIN])

    xlsx_path = outdir / f"{name}_preview.xlsx"
    write_xlsx(xlsx_path, [prev, log, leg])

    summary = {"csv_files": [str(p) for p in csv_paths], "preview": str(xlsx_path),
               "rows": len(rows), "counts": counts, "warnings": P.warnings}
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
