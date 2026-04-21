# YouTube API Client Design and Compliance Document

*YouTube Monitoring Pipeline — Sapienza University of Rome, in collaboration with Sony Computer Science Laboratories – Rome (Infosphere research line).*

*Prepared for the YouTube Researcher Program application, April 2026.*

---

## 1. Purpose

This document describes the design, operation, and compliance of a YouTube Data API v3 client ("the pipeline") used by academic researchers to collect public channel, video, and comment data from a curated list of European news outlets. The collected data is used exclusively for non-commercial academic research on polarization, toxicity, narrative formation, and audience trust in online news media. The pipeline is an internal-use research tool with no end users, no public interface, and no commercial function.

---

## 2. API Client Overview

- **Operator**: named research personnel at Sapienza University of Rome, in collaboration with the Infosphere research line at Sony CSL – Rome. The Principal Investigator is the named applicant on the YouTube Researcher Program application form.
- **Environment**: Sapienza University institutional research infrastructure.
- **Single project, single key**: the pipeline operates from one Google Cloud project using one API key. It does not rotate across projects to evade quota.
- **No end users**: the pipeline is not exposed to any third party. It has no user interface and serves no API data to downstream consumers. Research outputs (aggregated figures, peer-reviewed publications) are the only external artefacts.
- **Source list**: the target channel list of approximately 6,358 European news outlet channels is derived from the **NewsGuard** registry of news and information outlets, accessed under Sapienza University's institutional agreement with NewsGuard. Use of an independently-coded registry rather than team-coded labels is a methodological safeguard against coder bias on the key covariates (source credibility, editorial orientation).

---

## 3. Authentication and Access

- Access is by **API key only**, issued through the Google Cloud Console.
- The pipeline does **not** use OAuth2 and does not request access to any authenticated user's account or private data. Consequently, no OAuth Compliance Audit is required.
- The API key is stored in a YAML configuration file excluded from version control. It is not embedded in any client-facing artefact, not shared externally, and not transmitted outside the institutional environment.

---

## 4. API Endpoints Used

Data is collected exclusively through the official YouTube Data API v3. **No scraping, browser automation, or reverse-engineered endpoints are used.** No endpoints other than those listed below are called.

| Endpoint | Purpose | Cost |
|---|---|---|
| `channels.list` | Channel metadata and statistics | 1 unit |
| `playlistItems.list` (uploads playlist) | Enumerate videos on a channel | 1 unit per page of 50 |
| `videos.list` | Video details and engagement metrics | 1 unit per batch of 50 |
| `commentThreads.list` | Top-level comments with nested replies | 1 unit per page of 100 |
| `comments.list` | Additional replies when a thread exceeds its inline reply limit | 1 unit per page |
| `captions.list` | Caption track metadata (no transcript text) | 1 unit |
| `search.list` | Last-resort resolution of legacy custom-URL formats to a canonical channel ID | 100 units |

---

## 5. Collection Behaviour

- **Scope per channel**: for each resolved channel the pipeline retrieves channel metadata, all videos in the uploads playlist, all accessible top-level comments and replies, and caption track metadata (language, auto-generated flag, track type). **Transcript text is not downloaded.**
- **One-time exhaustive pass**: the pipeline performs a single comprehensive collection per channel, with optional targeted re-collection passes for longitudinal engagement analysis. It does **not** continuously poll, mirror, or "shadow" the platform.
- **Respect for platform signals**: the `commentsDisabled` flag is honoured as a legitimate creator choice. Content flagged `madeForKids` is recorded as metadata only; no distinct processing is applied and no such content is surfaced in analyses directed at children.
- **Polite-use pacing**: fixed delays are inserted between API calls (fractions of a second to a few seconds) to avoid throttling and to stay well within fair-use norms.
- **Idempotent persistence**: results are written to the research database with `INSERT OR REPLACE` semantics so that an interrupted run never produces inconsistent state, and a resumed run never re-calls the API for already-completed items.

---

## 6. Quota Management

- The pipeline tracks cumulative quota consumption at each call.
- When remaining quota falls below a configurable buffer (default 50,000 units), the pipeline halts gracefully, checkpoints its progress, and resumes the following day after the midnight-Pacific quota reset.
- On a `quotaExceeded` response, the client raises an explicit `QuotaExceededError` and halts cleanly, distinguishing quota exhaustion unambiguously from other failure modes.
- **The pipeline does not, and will not, attempt to exceed or circumvent daily quota limits**, as required by the YouTube API Services Terms of Service.

---

## 7. Data Storage and Security

- All collected data are stored in a single SQLite database on Sapienza University institutional storage (disk-encrypted workstations and/or institutional servers) with access limited to named research personnel.
- Stored fields include: channel-level metadata and statistics; video-level metadata, statistics, and caption availability; comment-level text, author identifiers as returned by the API, and engagement counts; and caption track metadata. No transcript text is stored.
- The database is **not** shared publicly, sold, licensed, or redistributed in raw form. Any replication artefacts released alongside publications consist of aggregate or pseudonymised derivatives.
- Logs, configuration files, and backups are held on the same institutional infrastructure under equivalent access controls. The API key is not included in any export or backup that leaves the institutional environment.

---

## 8. Data Retention and Deletion

- **Retention**: Program Data is retained for the duration of the research project and for the standard institutional record-keeping period thereafter, in accordance with Sapienza's research-integrity policy.
- **Refresh-based deletion**: on each refresh pass, records for channels, videos, or comments no longer accessible via the API (deleted, made private, or originating from terminated accounts) are removed from the active research database.
- **Notification-based deletion**: if YouTube or a rights-holder notifies the research team that specific content has been removed and must be removed from derivative stores, the corresponding records are removed from the research database within 30 days of notification.
- **Post-publication handling**: raw Program Data is not redistributed at any stage. Replication datasets, where released, contain only aggregate or pseudonymised derivatives.

---

## 9. Multi-Platform and Commercialisation Status

- The API client does **not** display YouTube data alongside data from other platforms in any user-facing interface, and is not part of a multi-platform product. Research analyses may contextualise YouTube findings against other public datasets at the aggregate level in academic publications, but no interface integrates YouTube data with other platforms.
- The pipeline and the Program Data it collects are used **exclusively for non-commercial academic research**. No Program Data is sold, licensed, redistributed, or used in any commercial product, advertising, or paid service.

---

## 10. Derived Metrics

Research outputs may include derived metrics permitted under the Researcher Program Terms of Service — for example, polarisation scores, toxicity scores, and inferred narrative or topic clusters assigned to videos, channels, or comment streams. These derived metrics are clearly labelled in publications as research-derived quantities distinct from any metric natively exposed by the YouTube API.

---

## 11. Ethical and Legal Framework

- All data are collected under the YouTube API Services Terms of Service, the YouTube API Developer Policies, and (upon acceptance) the YouTube Researcher Program Terms of Service.
- Only publicly posted content is collected. No private videos, private comments, direct messages, or authenticated-only content is accessed.
- The research is conducted under the institutional research-integrity and data-protection framework of Sapienza University of Rome. Where required by institutional policy, the project will obtain prior review from the relevant ethics or data-protection committee before any analytical output is published.
- Because the research is conducted at an EU institution on data that includes user-generated content authored by EU residents, it falls within the scope of Regulation (EU) 2016/679 (GDPR). Processing is conducted for scientific research in the public interest under Article 6(1)(e)/(f) read with the scientific-research safeguards of Article 89 GDPR. Data are minimised to fields necessary for the research questions; comment-author identifiers are aggregated, pseudonymised, or removed in published outputs unless individual-level attribution is essential to the research question and independently lawful.
- The NewsGuard source registry (Section 2) is a licensed third-party resource accessed under Sapienza's institutional agreement with NewsGuard. NewsGuard fields are used internally as research covariates and are not redistributed in raw form.

---

## 12. Publication and Attribution

- Findings will be made publicly available in peer-reviewed venues, preprint servers, or equivalent open-access channels, consistent with the Researcher Program's publication-of-findings requirement.
- Research outputs will attribute data provenance to the YouTube Data API v3 and acknowledge the YouTube Researcher Program where applicable, without making any statement that suggests partnership with, sponsorship by, or endorsement from YouTube.

---

## 13. Compliance Contact

The designated compliance contact for this API Client is the Principal Investigator named in the YouTube Researcher Program application form. Changes in compliance contact, institutional affiliation, or API-key ownership will be notified to YouTube in accordance with the Researcher Program Terms of Service.

---

*Document version: v4 — reviewer-focused design and compliance document, April 2026.*
