# Worked examples

## Epic (Job Story)
- **Title:** Enable customer self-service
- **Description:** When a customer needs a technician, they want to book and track jobs online so that they don't have to phone the service desk.
- **Acceptance criteria:**
  - Customers can book, track and cancel jobs online
  - Booking calls to the service desk drop by 30%

## Epic (System Story)
- **Title:** Modernise the data platform
- **Description:** Migrate the on-prem SQL Server to Azure SQL so that hosting cost drops and resilience improves.
- **Acceptance criteria:**
  - All portal data served from Azure SQL
  - On-prem server decommissioned

## Feature
- **Title:** Export job data to finance warehouse
- **Description:** Export job data nightly to the finance reporting warehouse so that finance reporting keeps working after cut-over.
- **Acceptance criteria:**
  - Nightly extract lands in the finance warehouse
  - Failed extracts alert the platform team

## Product Backlog Item (Job Story)
- **Title:** Text customer when technician is en route
- **Description:** When my technician is on the way, I want an SMS with their ETA so that I can be home when they arrive.
- **Acceptance criteria:**
  - SMS sent when job status changes to En route
  - SMS includes technician first name and ETA

## Product Backlog Item (System Story)
- **Title:** Migrate reference data
- **Description:** Migrate reference data tables to Azure SQL so that lookups work after cut-over.
- **Acceptance criteria:**
  - Row counts match source
  - Lookups return identical results

## Bug
- **Title:** Booking summary shows time in UTC
- **Description:** Fix the booking summary time zone so that customers see their local time.
- **Repro steps:**
  1. Book a job for 9:00 am
  2. Open the booking summary
  3. Time shows 11:00 pm (UTC)
- **Acceptance criteria (optional):** Summary shows the booked time in the customer's local time zone

## Task
- **Title:** Release old slot on reschedule
- **Description:** Release the original slot in the scheduling system so that others can book it.

## Risk
- **Title:** Azure SQL cost exceeds FY budget
- **Description:** Reduce Azure SQL tier cost so that the migration stays within the FY budget. Business Critical estimate is ~40% over.

## Impediment
- **Title:** Obtain address API key from vendor
- **Description:** Obtain the address API key from the vendor so that address validation can be built and tested.

## Rewrites (refinement)
| Before | After |
|---|---|
| Title `SSO stuff`, description `Need to do SSO`, no AC | Title `Sign in with company Entra ID account`; Description: When I open the portal, I want to sign in with my work account so that I don't manage another password. AC: Entra ID sign-in on portal login page; Local passwords disabled for staff |
| Title `As a PO I want reporting so that business can see data` | Title `Show weekly job volume report`; Description: When I review operations, I want a weekly job volume report so that I can plan technician capacity. |
