# Portal & Platform stand-up – 13/10/2026 (rough notes)

Attendees: Priya (PO), Liam, Sam, Aisha (infra)

- Liam: booking form is finished and merged. Started on address validation this morning.
- Liam: still waiting on the address API key from the vendor – can't test validation without it. Aisha to chase.
- Priya: demoed job booking to the business on Friday – they loved it. Main ask: customers want to **reschedule** a booking without calling. Needs a date/time change and a cancellation of the old slot.
- Priya: testing found the booking summary page shows the time in UTC, not local time (AEST). Customers will turn up confused.
- UAT environment back up since Thursday – network team fixed the firewall rule.
- Sam: reference data migration on track. Cost estimate for Azure SQL Business Critical tier came back ~40% over budget – could blow the FY budget.
- Aisha: decision from infra board – on-prem SQL server stays for the finance reporting workload this FY. Decommission is off the table for now.
- Aisha: finance needs a nightly extract of job data into their reporting warehouse once we cut over – nothing in the backlog covers this.
- Priya: the SMS notifications item is too vague – it's specifically "text the customer when the technician is on the way", with ETA.
