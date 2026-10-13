---
name: backlog-files
description: Reads an Azure DevOps backlog export (CSV or Excel) and builds the DevOps CSV import file plus a colour-coded Excel preview from a change set. Use whenever a backlog export must be read, or a DevOps upload CSV or backlog preview must be produced.
---

# Backlog files

Two scripts do all file work. Never hand-build the CSV or the Excel preview – the scripts guarantee the format, hierarchy and colour rules. Both scripts use the Python standard library only.

## Locate the scripts
The scripts are in this skill's `scripts/` folder. If a relative path doesn't resolve, find them:
```
find / -name build_outputs.py -path "*scripts*" 2>/dev/null
```
`references/process.json` (states, hierarchy, AC rules) sits next to `scripts/` and is loaded automatically.

## 1. Read the backlog
```
python read_backlog.py "<uploaded export file>" --out backlog.json
```
- Accepts `.csv` or `.xlsx` exported from an Azure DevOps query (tree or flat; with or without a Parent column).
- Prints an OUTLINE (`ID [Type] Title (State)`, indented by hierarchy) and QUALITY FINDINGS.
- Use the outline to place new work and the findings for refinement.
- If it warns that recommended columns are missing (State, Area Path, Iteration Path, Description, Acceptance Criteria), tell the user which columns to add to their query before proceeding with updates to those fields.

## 2. Write the change set
Write `changes.json` exactly as described in `references/changeset-schema.md`. Key rules:
- Actions are only `new`, `update`, `remove`. Never delete.
- Every `update` and `remove` has a dated `history` note.
- New items have no `state`. Parents are existing IDs or `ref`s of other new items.

## 3. Build the outputs
Existing backlog:
```
python build_outputs.py --backlog backlog.json --changes changes.json --outdir output
```
Brand-new backlog (no export):
```
python build_outputs.py --changes changes.json --outdir output
```
- On success it prints JSON with the file paths, counts and warnings.
- On `ERRORS` nothing is written. Fix `changes.json` and re-run. Don't ask the user unless the fix needs their decision.

## 4. Hand back
- Return both files from `output/` as downloads: `*_devops_import.csv` and `*_preview.xlsx`.
- Summarise in chat: counts (new / updated / removed), each new item that needed a justification, and any warnings.
- Remind the user: import via Boards > Queries > Import work items, review, then Save items.

## If scripts can't run
Say so plainly. Show the change set as a table in chat. Do not improvise a CSV or Excel file by hand.

## Preview colours (set by the script)
| Colour | Meaning |
|---|---|
| Green | New item |
| Yellow, orange cells | Updated item; orange = changed field |
| Red | Removed (state set to Removed/Closed, reason in History) |
| Grey | Unchanged context row carrying the hierarchy |
