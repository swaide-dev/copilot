# DevOps Backlog Analyst – declarative agent with skills

A Microsoft 365 Copilot declarative agent, built in Agent Builder, that:
- turns meeting transcripts and notes into Azure DevOps work items
- updates an existing backlog (states, History notes, removals)
- writes single work items in chat
- refines vague or incomplete backlog items

It outputs a DevOps import CSV and a colour-coded Excel preview. Python scripts produce both files, so the format is the same every time.

## Package contents

| Path | What it is |
|---|---|
| `agent/agent-instructions.md` | Name, description, instructions and conversation starters to paste into Agent Builder |
| `skill-zips/*.zip` | The four skill packages to upload |
| `skills/` | Unzipped source of the same skills, for editing |
| `samples/` | Dummy backlog export, sample meeting notes, sample change set and the outputs they produce |

### The skills

| Skill | Job |
|---|---|
| `devops-item-standards` | Writing standard: Job Story / System Story formats, KISS, AC rules per type, single-item mode |
| `meeting-to-backlog` | Meeting analysis → change set → files |
| `backlog-refine` | Backlog review → proposals → agreed changes → files |
| `backlog-files` | `read_backlog.py` and `build_outputs.py` (standard-library Python only), process rules, change-set schema |

## Before you start

- You need a Microsoft 365 Copilot licence.
- At the time of writing, Microsoft Learn lists custom skills in declarative agents as a preview for Frontier Program tenants, not available in Information Barriers tenants. Check that **Skills** appears on Agent Builder's **Configure** tab.
- Limits that apply:
  - 8 skills per agent
  - Each skill is a `.zip` of up to 50 MB with SKILL.md at the root
  - Instructions in SKILL.md must be under 20,000 characters
  - Agent instructions must be under 8,000 characters
- Skill scripts run in a sandbox with no network and no package installs. That's why the scripts use only the Python standard library.

## Step 1 – Smoke test (5 minutes)

This confirms that scripts run and that files come back as downloads before you build the full agent.

1. Create a test agent in Agent Builder. On **Configure → Skills → Add**, upload `backlog-files.zip`.
2. On **Try it**, attach `samples/dummy-backlog-export.xlsx` and `samples/sample-changes.json`, then say:
   *"Read the backlog with read_backlog.py, then run build_outputs.py with the attached change set and give me the files."*
3. Expected result:
   - an outline of 21 items
   - two downloadable files: the CSV and the preview xlsx
   - counts of 7 new, 5 updated, 1 removed and 5 context rows

If the script runs but no file is offered for download, ask the agent to "return the files as downloads". If scripts don't run at all, check the Skills preview is enabled for your tenant.

## Step 2 – Build the agent

1. In Copilot Chat, select **Agents & Skills → New agent**, then open the **Configure** tab.
2. Paste the **Name**, **Description** and **Instructions** from `agent/agent-instructions.md`.
3. Under **Skills → Add**, upload all four zips from `skill-zips/`.
4. Add the conversation starters.
5. Leave **Knowledge** empty. During the preview, an agent can't have both skills and embedded files, so attach the current export in each chat instead.
6. Test it on the **Try it** tab:
   - Attach `dummy-backlog-export.xlsx` and paste `sample-meeting-notes.md`, then say *"update the backlog from these notes"*.
   - Compare the result with `samples/output/`.
   - Try *"write a work item for adding a password reset link"*, with the export attached.
   - Try *"refine the backlog"*. It should flag items 1011, 1026 and 1027.
7. Create the agent and share it as needed.

## Exporting your backlog (do this each time)

Create a query in Azure DevOps (this is a one-off):
- **Type of query:** Tree of work items (Parent/Child), or a flat list with the **Parent** column.
- **Columns:** ID, Work Item Type, Title, State, Area Path, Iteration Path, Description, Acceptance Criteria, Repro Steps, Tags, Parent. Add Assigned To, Priority and Effort if you want the agent to update them.
- **Filter:** your project's area path; include closed items if you want full context.

Then run the query and use **Export to CSV**. You can also open the CSV in Excel and save it as `.xlsx`; both formats work.

**Why columns matter:** the agent only writes columns that are in your export. It refills context rows with their exported values so that nothing is blanked on import. If a change needs a column that isn't exported, the script stops and tells you which column to add.

## Importing the result

1. Go to **Boards → Queries → Import work items**, choose the CSV, then select **Import**.
2. Review the grid. Fix any rows shown in red, then select **Save items**.
3. New items import as New (or To Do, Open or Proposed). To give a new item a different state, export it, change the State and re-import.
4. Parent links come from Title column indentation. Keep the grey context rows in the file.

## Preview colours

| Colour | Meaning |
|---|---|
| Green | New item |
| Yellow row, orange cells | Updated item; orange marks the changed fields |
| Red | Removed. State is set to Removed (Closed for Risk and Impediment), never deleted, with the reason in History |
| Grey | Unchanged context row carrying the hierarchy |

The workbook also has a **Change log** sheet, with one row per field change including the justification and source quote, and a **Legend** sheet.

## Process rules (`skills/backlog-files/references/process.json`)

States default to the Azure DevOps **Scrum** process, plus **Risk** taken from CMMI:

| Type | States | Remove sets | Parent |
|---|---|---|---|
| Epic | New, In Progress, Done, Removed | Removed | top level |
| Feature | New, In Progress, Done, Removed | Removed | Epic |
| Product Backlog Item | New, Approved, Committed, Done, Removed | Removed | Feature |
| Bug | New, Approved, Committed, Done, Removed | Removed | Feature |
| Task | To Do, In Progress, Done, Removed | Removed | PBI or Bug |
| Impediment | Open, Closed | Closed | any, or top level |
| Risk | Proposed, Active, Resolved, Closed | Closed | Epic, Feature, PBI, or top level |

If your inherited process differs (for example, you added a Removed state to Risk, or renamed states), edit `process.json`, re-zip `backlog-files` and re-upload it.

## Known limits

- **Changing a work item's type or parent:** CSV import can't do this. The refine skill lists these as manual actions instead.
- **Brand-new backlogs:** the CSV omits the ID and State columns, as Azure DevOps requires.
- **Large imports:** Azure DevOps accepts 1,000 rows per CSV. The script splits larger imports by top-level item into `_part1`, `_part2` and so on.
