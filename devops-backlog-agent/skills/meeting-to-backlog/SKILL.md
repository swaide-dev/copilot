---
name: meeting-to-backlog
description: Analyses project meeting content (Teams transcript, Facilitator notes or rough manual notes) and turns it into Azure DevOps backlog changes - new items, status and state updates, removals - output as a DevOps import CSV and colour-coded Excel preview. Use when the user supplies meeting notes or a transcript and wants backlog items, with or without an existing backlog export.
---

# Meeting to backlog

Turn meeting content into a validated change set, then build the files with the backlog-files skill. Write every item to the devops-item-standards skill.

## Inputs
- **Meeting content:** Teams transcript, Facilitator notes, or rough notes (pasted or attached).
- **Backlog export:** CSV or Excel from an Azure DevOps query. If the user says the project has a backlog but none is attached, ask for the export before continuing. If it's a new project, use `new_backlog` mode (no export).

## Procedure

### 1. Read the backlog
Run `read_backlog.py` (backlog-files skill). Keep the OUTLINE in view for matching and placement.

### 2. Extract signals from the meeting
List, with a short source quote for each:
- **Status:** started, finished, blocked, unblocked, accepted, demoed.
- **Decisions:** scope in or out, priority calls, deferrals.
- **New work:** requests, gaps, follow-ups that need delivery effort.
- **Defects:** something not working as intended.
- **Risks:** something that might go wrong (cost, dependency, schedule).
- **Impediments:** something blocking work now.

Ignore chit-chat and actions that aren't backlog work (e.g. "Aisha to send the minutes"). With rough notes, be conservative: only record what the notes actually say.

### 3. Match each signal to the backlog
- Match on meaning, not just words. Check titles, descriptions and parents.
- **Discussed existing item → `update`.** Always write a dated History note: `DD/MM/YYYY <meeting>: <what was said>`.
- Change **State** only when the meeting states it clearly:

| Said in meeting | Task | PBI / Bug | Epic / Feature | Impediment | Risk |
|---|---|---|---|---|---|
| started / working on it | In Progress | Committed* | In Progress | – | Active |
| finished / merged / complete | Done | Done** | Done** | Closed | Closed |
| ready for sprint / estimated | – | Approved | – | – | – |
| resolved / no longer blocking | – | – | – | Closed | Resolved |

\* only if committed to the current sprint. \** only when the PO accepted it, or all child work is done; otherwise add a History note only.

- **Dropped, cancelled or out of scope → `remove`**, with the reason and who decided in History. Never delete.
- Status noise with no state change (e.g. "on track") → a History-only update, but only for items explicitly discussed.

### 4. Place new work
- Put each new item under the most specific existing parent that genuinely fits (Feature for PBI/Bug, PBI/Bug for Task).
- **If nothing fits**, propose a new parent (e.g. a new Feature under the closest Epic, or a new Epic). The `justification` must say why existing items don't cover it and why this position.
- Every new item needs a `justification` and a `source` quote.
- Create Tasks only when the meeting describes the breakdown. Don't invent tasks.
- Risks and Impediments go under the item they affect (top level if project-wide).

### 5. Write `changes.json`
Follow `references/changeset-schema.md` in the backlog-files skill. Write titles, descriptions and AC to the devops-item-standards skill.

### 6. Build and fix
Run `build_outputs.py`. If it reports ERRORS, fix the change set and re-run until it succeeds.

### 7. Report back
Return both files, then a short summary:

```
Meeting: <name/date> | New: X | Updated: Y | Removed: Z

New work needing your review
- N7 Feature "Export job data to finance warehouse" under Epic 1020 – <justification>

State changes
- 1004 Task: In Progress → Done
- 1025 PBI: New → Removed (infra board decision)

Needs your decision (not in the CSV)
- "Priya said reschedule is top priority" – raise priority of N2? 
```
Keep anything ambiguous out of the change set and list it under "Needs your decision".
