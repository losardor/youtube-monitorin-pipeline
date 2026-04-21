# YouTube Researcher Program Application — Field-by-Field Guide

*For the Sapienza Principal Investigator submitting the application. April 2026.*

This note walks through every field of the YouTube Researcher Program application form and indicates what to enter. Two documents accompany the submission:

1. **Research proposal** (the long-form document with abstract) — the abstract is the text for the Proposal field; the full document should be shared as a Google Doc link.
2. **API Client Design and Compliance Document** — uploaded as a PDF under the API Client section.

Both are provided separately. The form itself can be reached at:
`https://support.google.com/youtube/contact/yt_researcher_certification`

---

## Before starting the form

Three things to prepare first, because the form itself has no save/resume:

1. **Create or confirm a Google Cloud project** that will host the API key used for collection. You will need its **project number** (a string of digits visible in the Google Cloud Console alongside the Project ID). If the pipeline is already running, this is the same project whose key is in `config/config_comprehensive.yaml`.
2. **Share the long-form research proposal** as a Google Doc with sharing set to **"Anyone with the link — Viewer"** (not Commenter, not Editor). Copy the share URL. This is what goes in the Proposal field.
3. **Convert the API Client Design and Compliance Document to PDF** and confirm it is under 10 MB. This is the file uploaded under the API Client section. The form rejects multi-file uploads and anything over 10 MB.

---

## Section 1 — Application type

| Field | What to enter |
|---|---|
| Please select the option applicable | **New Researcher Program Application** |

---

## Section 2 — General Information

| Field | What to enter |
|---|---|
| Your full legal name | PI's full legal name as it appears on Sapienza records. |
| Organization contact email address | PI's **institutional** email (`@uniroma1.it`). Do not use a personal or Sony CSL address — the form explicitly prefers an institutional email and Sapienza is the applying institution. |
| Country | **Italy**. |
| Organization Name | **Sapienza Università di Roma** (select from the drop-down). If not listed verbatim, use "Other" and enter exactly *Sapienza University of Rome* or *Sapienza Università di Roma* as Sapienza appears on its accreditation records. |
| Organization Website | `https://www.uniroma1.it/` (or the PI's departmental/faculty URL if more specific). |
| Organization Address | The PI's department/faculty postal address at Sapienza. |
| Job Title | **Faculty** (for a professor). |
| Department Name | PI's department name, in the form used in the Sapienza directory. |
| Link to profile in institution's faculty or researcher directory | The public `uniroma1.it` faculty profile URL for the PI. Confirm beforehand that the page resolves and is publicly accessible — reviewers do click through. |

---

## Section 3 — Project Information

| Field | What to enter |
|---|---|
| Reason for filling the form | **Research**. |
| Research Title | **Polarization, Toxicity, and Trust in the European News Ecosystem on YouTube** — or the PI's preferred variant, if it should align with an existing grant or project title. |
| Research Start Date | The date the research phase formally begins under this application. Use a date within the next ~30 days of submission (e.g., the first of the month following submission). The URL-validation phase is already underway; this date refers to the main collection and analysis programme that the quota increase unlocks. |
| Research Publication Date | Twelve months from the start date. Use a specific date rather than "TBD". *Important:* the Terms of Service state that quota access may be revoked following publication, so this date should reflect the first publication, not the end of all follow-on analyses. |
| Proposal | **Paste the abstract** from the research proposal document verbatim into this field. The abstract is 1,407 characters and fits the 1,500-character limit with room to spare. Include **the Google Doc link to the full proposal** at the end of the pasted text if space allows, or mention in the abstract that a full proposal is attached. |
| Field of Research | **Computational Social Science** if available in the drop-down; otherwise **Social Sciences** or **Communication Studies**, whichever is closest. |
| Is your research affiliated or sponsored by government or non-government entity? | **Yes**. Sapienza is a public university; the Sony CSL Rome collaboration operates under a public-private agreement with CREF (Enrico Fermi Research Centre, a public body). If a follow-up text field appears, briefly note: *"Conducted at Sapienza University of Rome (public institution) in scientific collaboration with the Infosphere research line at Sony CSL – Rome."* |

**Practical note on the Proposal field:** if the form accepts only plain text, the Google Doc link can still be pasted as a URL — reviewers will click through. The pasted abstract must end with something like: *"Full proposal: [link]. API Client design and compliance document attached."*

---

## Section 4 — API Client Information

This is the section most directly scrutinized for compliance, and where the attached design document does most of the work.

| Field | What to enter |
|---|---|
| Project numbers for API Client(s) | The single Google Cloud **project number** (digits) for the project whose API key is used by the pipeline. Comma-separated only if there are multiple projects — but there is only one. |
| Is this a publicly or privately available API Client? | **Internal use only**. |
| Demo account / access instructions | Leave blank. No login is required, because the client is not user-facing. If a value is required, enter: *"The API Client is an internal research script with no user interface. A detailed design and compliance document is attached describing all functionality and data handling."* |
| Does your API Client commercialize YouTube Data? | **No**. |
| Does your API Client use multiple projects to access YouTube APIs? | **No**. |
| Does this API Client display data from, or provide features or services across, multiple platforms? | **No**. Research analyses may reference other public datasets at aggregate level in academic publications, but no interface integrates YouTube data with other platforms. |
| How long do you store YouTube API Data? | Select the option closest to **"For the duration of the research project and the standard institutional record-keeping period."** If the form offers fixed ranges (e.g., "less than a year", "1–3 years", "more than 3 years"), choose the one matching your institutional policy — typically 3+ years for research data under Italian/EU record-keeping norms. |
| How often do you refresh YouTube API Data? | Select the closest option to **"One-time collection with targeted re-collection for a longitudinal sub-sample."** If only frequency options are offered (daily/weekly/monthly/less frequent), choose **"Less frequently than monthly"**. The pipeline is not a continuous poller. |
| Upload documents (design / screencast) | Upload the **API Client Design and Compliance Document** as a single PDF under 10 MB. This is the non-negotiable upload. |

---

## Section 5 — Acknowledgements

All four checkboxes are required. Read each one before checking:

- **API ToS and Developer Policies** — *I agree*.
- **Demo account / Google access disclaimer** — *I understand*. (Relevant only if you provided a demo account; otherwise still tick it.)
- **Researcher Program Policy & Terms** — *I agree*. This is the substantive one — the design document's Section 11 and the research proposal both commit to compliance with these Terms. Read the Terms at the linked URL before ticking.
- **Truthfulness attestation** — *I agree*.

The optional feedback-by-email box is the PI's choice.

---

## After submitting

A few things to do or expect after the submit button:

1. **Save a screenshot or print-to-PDF of the submitted form** before closing the browser. The form does not email a copy of the submission, and the confirmation message is brief.
2. **Preserve the confirmation email**, if one arrives, in a project folder along with the research proposal and design document. Review timelines have varied historically from days to several weeks.
3. **Do not change Google Cloud project ownership, API key, or institutional affiliation** while the application is pending. If institutional affiliation changes for more than 30 calendar days, the Researcher Program Terms treat this as a breach and may terminate access.
4. **Be ready for follow-up questions.** Reviewers occasionally ask for clarification on commercialization, multi-platform use, or storage arrangements. The API Client design document pre-empts most such questions, but a responsive turnaround on any follow-up email strengthens the application.
5. **Do not publicly announce acceptance** — the Terms prohibit statements suggesting partnership with or endorsement from YouTube without prior written approval.

---

## Quick reference: what each document covers

| Document | Purpose | Where it lives |
|---|---|---|
| **Research proposal** (long form) | Scientific argument for the project. | Shared Google Doc, linked from the Proposal field. |
| **Research proposal abstract** | 1,407-character summary of the above. | Pasted verbatim into the Proposal text field. |
| **API Client Design and Compliance Document** | Technical specification and Terms-of-Service compliance enumeration. | Uploaded as PDF in the API Client section. |
| **This guide** | Submission checklist. | Internal; not submitted. |

---

*If any field in the form does not match this guide (e.g., new questions have been added since this document was prepared), default to the principle that the application is from Sapienza, for non-commercial academic research, using only the public Data API, under Sapienza's institutional research-integrity and GDPR framework. Any ambiguous field answered consistently with that framing will be correct.*
