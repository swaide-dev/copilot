---
name: devops-item-standards
description: House standard for writing Azure DevOps work items (Epic, Feature, Product Backlog Item, Bug, Task, Risk, Impediment) using System Story and Job Story formats and KISS. Use whenever a work item is written, rewritten or reviewed, and when the user asks to "write a work item for ..." without meeting notes.
---

# DevOps work item standards

Apply these rules to every work item you write or rewrite. KISS: plain words, one idea per item, no padding.

## Story formats (Valerio Zanini)

**Job Story** – use when a clearly defined user or persona gets the benefit.
> When [situation], I want [action], so that [objective].

**System Story** – use for internal, enabler, technical, bug, risk and impediment work.
> [Action verb] [subject] so that [goal].

Never write "As a Product Owner…" or "As a developer…". Write from the point of view of whoever benefits from the result, not who requests or builds it. Stories describe the need and why – not how to build it.

## Format by type

| Type | Statement in Description | Acceptance criteria |
|---|---|---|
| Epic | Job Story (user outcome) or System Story (platform) | Required. 2–4 outcome bullets. |
| Feature | Job Story or System Story | Required. 2–4 bullets. |
| Product Backlog Item | Job Story (user-facing) or System Story (technical) | Required. 2–5 testable bullets. |
| Bug | System Story: "Fix [defect] so that [expected behaviour]" + Repro Steps | Optional. 1–2 bullets. |
| Task | System Story | None. |
| Risk | System Story: "Mitigate/Reduce [risk] so that [impact avoided]". Add one line of context. | None. |
| Impediment | System Story: "Resolve/Obtain [blocker] so that [blocked work continues]". | None. |

## Titles
- Verb + subject. Under 80 characters. No story syntax in the title.
- Good: `Reschedule a booking online`, `Migrate reference data`, `Booking summary shows time in UTC` (bugs may state the defect).
- Bad: `SSO stuff`, `SMS notifications`, `As a customer I want to reschedule…`.

## Acceptance criteria
- Each bullet is one observable, testable outcome. No implementation detail.
- Brief: 3–12 words per bullet where possible.
- Good: `Old slot is released`. Bad: `The system should, when the user clicks reschedule, call the API to free the slot…`.

## Description layout
1. The story statement (one sentence).
2. Optional: one or two lines of essential context (constraint, dependency, decision). Nothing else.

## Hierarchy
Epic → Feature → Product Backlog Item or Bug → Task. Risk and Impediment sit under the item they affect, or top level. Place work under the most specific existing parent that genuinely fits. If nothing fits, propose a new parent and justify it.

## Single item mode ("write a work item for …")
When the user asks for one item without meeting notes:
1. If a backlog export is attached, read it with the backlog-files skill (`read_backlog.py`) for context: find the right parent, avoid duplicates, match naming and area/iteration paths.
2. Pick the type if the user didn't (explain the choice in one line).
3. Post the item in chat in this layout – no CSV or Excel file:

```
Type: Product Backlog Item
Parent: 1002 – Book a job online
Title: Reschedule a booking online
Description:
When my plans change, I want to reschedule my booking online so that I don't have to call the service desk.
Acceptance criteria:
- Customer can pick a new available slot for an open booking
- Old slot is released
- Updated confirmation shown with the same job ID
Area Path: Contoso Field Service\Portal Team
Iteration Path: Contoso Field Service
Why here: Feature 1002 covers booking; no existing PBI covers changing a booking.
```
Omit Acceptance criteria for Task, Risk and Impediment. Add Repro steps for Bugs. Flag a likely duplicate if one exists.

See `references/examples.md` for worked examples of every type.
