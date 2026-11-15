# Claimly — AI Personal Value Recovery Assistant

**Product:** B2C web application for US consumers.  
**Pitch:** *Unlock the value you've already paid for.*  
**MVP focus:** Purchase receipts, manufacturer/retailer warranties, and refund follow-ups. Other benefits (credit cards, subscriptions, employer perks) are later extensions.

## 1. User experience

**Upload documents → describe the issue → review possible entitlement → prepare a claim → track outcome.**

Example: A user uploads a laptop receipt and warranty PDF, then writes, “The screen stopped working after 14 months.” Claimly checks the documents, identifies the potentially applicable clauses and missing evidence, then produces an actionable checklist and editable claim message.

## 2. What the AI agent does

The agent is a **document-grounded claim-preparation assistant**, not an insurer, warranty administrator, lawyer, or autonomous claims filer. It must cite the uploaded evidence, distinguish uncertainty from confirmed facts, and ask for missing information when necessary.

| Function | Inputs | Agent action | Outputs |
|---|---|---|---|
| **A. Document intake** | Receipt, invoice, warranty PDF, return confirmation, or image | Read text using document parsing/OCR; identify document type and detect unreadable pages | Parsed text, document type, extraction confidence and review flags |
| **B. Structured extraction** | Parsed documents | Extract merchant/manufacturer, product, purchase date, price, serial/order number where present, coverage dates, exclusions, return/refund terms and instructions | Editable structured **purchase/coverage record**, with source references |
| **C. Deadline & status tracking** | Extracted dates, user corrections, case status | Calculate deadlines when the documents provide sufficient rules; flag ambiguity and trigger reminders | Deadline timeline, upcoming-action reminders, status dashboard |
| **D. Issue intake** | User's account of defect, return, missing refund, relevant dates and supporting files | Ask focused questions to fill material gaps (e.g., date of failure, damage cause, return date) | Structured **case record**, missing-information checklist |
| **E. Evidence-grounded assessment** | Case record + relevant policy text | Match reported facts against coverage conditions and exclusions; surface conflicting or missing information | **Possible coverage / insufficient evidence / likely excluded**, with explanation and exact supporting excerpts; **not a guarantee** |
| **F. Claim preparation** | Verified extracted fields, user narrative, policy instructions | Assemble claim requirements and draft an editable merchant/manufacturer support message | Claim checklist, attachments list, editable email/message, verified submission directions if provided |
| **G. Follow-up assistant** | Submission date, response, refund status, user-entered updates | Summarize correspondence, highlight next steps, draft follow-ups | Case timeline; pending/approved/denied/resolved states; follow-up draft |
| **H. Outcome accounting** | User-confirmed reimbursements or reliable records | Distinguish merely possible value from approved and actually received value | Potential, approved, and **confirmed recovered** amounts tracked separately |

## 3. Required inputs

**User-provided:**
- Receipt or invoice (PDF/photo), relevant warranty or refund terms (PDF/screenshot), optionally messages/return confirmation.
- Short issue description: what happened, when, and what remedy is wanted.
- Missing fields if extraction is uncertain; optional status updates and confirmed recovery amount.

**System-provided:**
- Document parser/OCR and a vision-capable LLM for structured extraction.
- User account, secure file storage, case database, date calculation and notifications.
- Optional official merchant policy/contact lookup **only when verifiable**; never fabricate coverage or URLs.

## 4. Main outputs (UI)

1. **My Items:** product, vendor, purchase date, receipt, warranty/return terms and source references.
2. **Opportunity Card:** suspected issue, relevant clause, deadline, uncertainties, required next action.
3. **Claim Package:** editable claim message, required attachments, checklist and submission link/instructions when verified.
4. **Case Tracker:** drafted → submitted → awaiting response → approved/denied → resolved.
5. **Recovery Dashboard:** possible, approved and confirmed recovered value shown **separately**.

## 5. Minimal data objects

```text
Document {id, user_id, type, file_url, extracted_text, created_at}
Item {id, user_id, merchant, product, purchase_date, price, source_document_ids}
Coverage {id, item_id, provider, start_date, end_date, terms, exclusions, evidence_refs}
Case {id, item_id, issue, incident_date, status, assessment, missing_info, claimed_amount}
CaseEvent {id, case_id, date, type, note, attachment_id}
```

## 6. MVP scope (12–24 hours)

**Build:** account/login; PDF/image upload; real document extraction; editable records; basic deadline logic; issue intake; source-grounded assessment; claim checklist and editable message; persistent case status. Test the end-to-end flow with **fictional/sample documents**.

**Do not build initially:** bank/email scraping, automatic claim filing, live insurer/merchant integrations, guaranteed eligibility decisions, payout handling, every possible perk category, or autonomous actions on third-party accounts.

**Recommended implementation:** Next.js + Supabase Auth/Postgres/Storage + document parsing/OCR + LLM structured JSON extraction + deterministic deadline rules. Store evidence pointers (page/excerpt) and support user corrections.

## 7. Safety, privacy and success metrics

- **No invented entitlements:** If proof is insufficient, state *unknown* and specify what's missing. A manufacturer's warranty is not automatically an extended credit-card warranty.
- **User in control:** Never submit claims, contact companies, or send documents without explicit approval.
- **Privacy:** Secure storage, minimal retention, document deletion, clear consent, and masking of sensitive identifiers when possible.
- **Measure success:** extraction accuracy, percentage of actionable cases, time to prepare claim, claim submissions, confirmed recoveries, and repeat usage—not total hypothetical “money found.”

**Core product differentiation:** Not a receipt vault; a **source-grounded path from purchase documents to a real recovery action**.
