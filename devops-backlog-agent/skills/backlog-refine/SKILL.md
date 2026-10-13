---
name: backlog-refine
description: Reviews an existing Azure DevOps backlog export for missing content, ambiguity, poor story format, weak acceptance criteria, wrong hierarchy and duplicates, proposes KISS rewrites, and outputs approved changes as a DevOps import CSV and colour-coded Excel preview. Use when the user asks to read, review, clean up or refine the backlog.
---

# Backlog refinement

Refinement is a conversation: find problems, propose fixes, agree, then build files.

## 1. Read and assess
Run `read_backlog.py` (backlog-files skill). Start from its QUALITY FINDINGS, then review every open item (not Done/Removed/Closed) yourself for:
- **Missing content:** no description, no AC on Epic/Feature/PBI.
- **Ambiguity:** vague titles ("SSO stuff"), no clear outcome, untestable AC, several ideas in one item.
- **Format:** description not in Job Story or System Story form; story written from the PO's or developer's view.
- **AC quality:** implementation detail, too many bullets, not testable, AC on Tasks.
- **Hierarchy:** item under the wrong parent type, orphans, a PBI that is really a Feature (too big) or a Task (too small).
- **Duplicates or overlaps** between items.
- **Stale items:** open items whose parent is Done or Removed.

If the user named specific items or an area, limit the review to those.

## 2. Propose (in chat, before any file)
Group by item, worst first. For each item show current vs proposed, written to the devops-item-standards skill:

```
1027 PBI "SSO stuff"  –  vague title, no story, no AC
  Title: Sign in with company Entra ID account
  Description: When I open the portal, I want to sign in with my work account so that I don't manage another password.
  AC: - Entra ID sign-in on the portal login page
      - Local passwords disabled for staff accounts
  Question: Is this staff-only, or customers too?
```

- Never invent facts. Where the backlog doesn't say enough, propose wording with a placeholder and ask a question.
- Changes the CSV can't make – work item type change, re-parenting, merging duplicates – list as **Manual actions** with the steps to do them on the board.
- Suggest `remove` only for clear duplicates or items the user confirms are dead.

## 3. Agree
Ask the user to accept all, accept some by ID, or amend. If the user already said "just do it", proceed with everything except items that have open questions.

## 4. Build
Write `changes.json` with `mode: "refine"`:
- One `update` per accepted item, with only the changed fields.
- History on every update: `DD/MM/YYYY Backlog refinement: <what changed and why>`.
- Accepted removals as `remove`, with the reason in History.

Run `build_outputs.py`, fix any ERRORS, and return both files. Finish with:
- the counts,
- the Manual actions list,
- unanswered questions.
