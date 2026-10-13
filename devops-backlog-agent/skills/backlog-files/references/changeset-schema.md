# Change set format (changes.json)

The analysis skills write this file. `build_outputs.py` validates it and builds the CSV and Excel preview.

```json
{
  "meta": {
    "project": "Contoso Field Service",
    "source": "Sprint 14 review 13/10/2026",
    "mode": "update | new_backlog | refine"
  },
  "changes": [ ...one object per change... ]
}
```

## Actions

Only three actions exist. There is no delete.

### new
| Key | Required | Notes |
|---|---|---|
| `action` | yes | `"new"` |
| `ref` | yes | Your label, e.g. `"N1"`. Children use it as `parent`. |
| `type` | yes | Epic, Feature, Product Backlog Item, Bug, Task, Impediment, Risk |
| `parent` | see notes | Existing ID (number) or a `ref`. `null` only for Epic, Risk, Impediment, or a justified orphan. |
| `title` | yes | Verb + subject. Under 80 characters. |
| `description` | yes | The System Story or Job Story statement. Plain text; the script converts to HTML. |
| `acceptance_criteria` | Epic, Feature, PBI | List of 2–5 short strings. Never for Task, Risk, Impediment. Optional for Bug. |
| `repro_steps` | Bug | Numbered lines (`1. ...`). |
| `tags`, `area_path`, `iteration_path`, `priority`, `effort` | no | Area/Iteration inherit from the parent when omitted. |
| `history` | no | Optional note for the Discussion. |
| `justification` | yes (existing backlog) | Why the item is needed and why it sits under that parent. |
| `source` | recommended | Short quote from the notes that triggered it. |

Never set `state` on a new item.

### update
| Key | Required | Notes |
|---|---|---|
| `action` | yes | `"update"` |
| `id` | yes | Existing work item ID |
| `history` | yes | What changed and why, dated. Becomes a System.History (Discussion) comment. |
| `state` | no | Must be valid for the type (see process.json). |
| `title`, `description`, `acceptance_criteria`, `repro_steps`, `tags` | no | Only include fields that change. |
| `fields` | no | Any other exported column, e.g. `{"Iteration Path": "Proj\\Sprint 15"}` |
| `justification`, `source` | recommended | |

A History-only update (no field changes) is valid – use it for status notes.

### remove
| Key | Required | Notes |
|---|---|---|
| `action` | yes | `"remove"` |
| `id` | yes | Existing work item ID |
| `history` | yes | Why it was removed, dated. |

The script sets State to the type's remove state (Removed; Closed for Impediment and Risk). The row is shown in red.

## Rules the script enforces (fix and re-run if it reports ERRORS)
- New items: no State; valid parent type; AC rules by type; justification when an existing backlog is supplied.
- Updates/removes: ID must exist; History required; State must be valid; no re-parenting.
- Every column written for existing items must already be in the export, so no existing field is blanked.
