# Recommendle Requirements Specification

## 1. Purpose
This document defines the project requirements for Recommendle (Decidio Preference Modeling), based on:
- The original sponsor problem statement
- The currently implemented backend, frontend, and scripts in this repository

The goal is to capture what the system must do, how well it must do it, and what constraints apply.

## 2. Problem Statement Summary (Source-Aligned)
Users making a sequence of related product decisions (for example, choosing a set of items for a shared style/theme) are often overwhelmed because choices are interdependent, not independent. The system should help users discover and model preferences over a sequence of decisions, support both visual and feature-based interaction modes, and account for exceptions/inversions in preference patterns.

## 3. Scope
### In Scope (Current Product)
- Web-based interactive preference game
- Sequential preference modeling using user picks over multiple rounds
- Feature-aware recommendation and prediction
- Category-based product catalogs (currently fountain pens; movies supported with ingestion)
- Hidden preference detection and explainable summary

### Out of Scope (Current Product)
- Native mobile app
- Full account/auth system
- Explicit drag-reorder/swipe UX
- Production deployment requirements (HA, autoscaling, SSO, etc.)

## 4. Functional Requirements
Status legend:
- `Implemented` = present in current codebase
- `Partial` = partly present, but not fully as originally envisioned
- `Planned` = logical next requirement from statement, not implemented yet

| ID | Requirement | Status |
|---|---|---|
| FR-01 | The system shall maintain a product catalog for at least one domain and support expansion to multiple categories. | Implemented |
| FR-02 | The system shall allow a user to start a new session/game with player name and category selection. | Implemented |
| FR-03 | The system shall present an onboarding pool of 50 candidate items for the chosen category. | Implemented |
| FR-04 | The system shall require exactly 10 onboarding selections before proceeding. | Implemented |
| FR-05 | The system shall collect a set-level prefix rating after onboarding (coherence rating of selected set). | Implemented |
| FR-06 | The system shall run sequential rounds (currently 5) where the user picks one item from generated candidates (currently 10). | Implemented |
| FR-07 | The AI model shall update user preference state after each choice and generate the next round candidates. | Implemented |
| FR-08 | The system shall score AI vs human outcomes per round and cumulatively across the session. | Implemented |
| FR-09 | The system shall provide per-round explanation including AI pick, user pick, and top candidate rankings. | Implemented |
| FR-10 | The system shall expose both visual-first and feature-first interaction modes. | Implemented |
| FR-11 | The system shall detect latent/hidden preferences and provide progressive hints during later rounds. | Implemented |
| FR-12 | The system shall provide an end-of-game summary including learned preferences and hidden-gem recommendations. | Implemented |
| FR-13 | The system shall maintain a leaderboard of completed sessions, filterable by category. | Implemented |
| FR-14 | The system shall show per-player historical performance and drill-down details for past games. | Implemented |
| FR-15 | The system shall provide data ingestion tooling for category datasets (scrape/load/migrate/ingest). | Implemented |
| FR-16 | The system shall support preference exceptions/inversions (user likes an item that violates usual pattern). | Partial |
| FR-17 | The system shall provide explicit swipe/right-brain vs swipe/left-brain navigation mechanics. | Partial |
| FR-18 | The system shall allow users to reorder chosen items as an input signal for preference strength. | Planned |
| FR-19 | The system shall allow direct feature selection as a primary narrowing control (not only model explanation). | Planned |
| FR-20 | The system shall support named saved collections/lists per user profile beyond single game sessions. | Planned |

## 5. Non-Functional Requirements
| ID | Requirement | Notes / Current State |
|---|---|---|
| NFR-01 | Usability: The primary flow shall be understandable without training and completable in a single sitting. | Implemented via onboarding + round-by-round UI. |
| NFR-02 | Responsiveness: Core game API calls shall return quickly enough for interactive use. | Implemented; no formal SLA defined yet. |
| NFR-03 | Explainability: Model output shall include interpretable rationale and feature-level signals. | Implemented in round results and final summary. |
| NFR-04 | Extensibility: New categories shall be addable with minimal code changes. | Implemented through category profiles + ingestion scripts. |
| NFR-05 | Data integrity: Product identity and core fields shall remain consistent under ingestion/migration. | Implemented via schema migration and DB indexes. |
| NFR-06 | Testability: Core model and service behavior shall be verifiable through automated tests/scripts. | Implemented (backend tests + evaluation tooling). |
| NFR-07 | Accessibility baseline: Inputs shall have labels, keyboard-usable controls, and visible feedback. | Implemented baseline; full WCAG audit pending. |
| NFR-08 | Portability: System shall run in local development on standard academic/dev machines. | Implemented (Python + Node + MongoDB local stack). |
| NFR-09 | Visual adaptability: UI shall support both light and dark themes. | Implemented. |
| NFR-10 | Privacy baseline: System shall minimize personal data collected during gameplay. | Implemented (player name + gameplay data only). |

## 6. Constraints
### 6.1 Sponsor / Program Constraints
- Students may be required to sign over IP to sponsor (as indicated in sponsor statement).
- Original sponsor statement did not impose hard technical-stack constraints.

### 6.2 Technical Constraints (Current Implementation)
- Backend: Python + FastAPI
- Frontend: React + Vite
- Database: MongoDB (local/default expected in docs)
- Runtime prerequisites: Python 3.10+, Node 18+, local MongoDB instance
- Category must have sufficient inventory (50 items minimum) to start a game flow

### 6.3 Data / Integration Constraints
- Movie ingestion requires a valid TMDB API key and adheres to TMDB API usage limits/terms.
- Scraped/ingested product data quality impacts model output quality.
- Current recommendation quality is bounded by available session data and feature engineering.

### 6.4 Product Constraints
- Current system is web-first, not native mobile.
- Authentication, authorization, and multi-tenant account management are not implemented.
- Current rounds are fixed in code to 5 for game mode.

## 7. Requirement Traceability to Initial Statement
From the sponsor document:
- "Model preferences in both visual and features domain" -> FR-10, FR-09, FR-19
- "Build initial database of products with features and photos" -> FR-01, FR-15
- "Sequentially update based on user input" -> FR-06, FR-07
- "Model evaluates coherence/goodness of list" -> FR-05, FR-12, NFR-03
- "Benchmark accuracy/consistency with users" -> NFR-06, FR-13, FR-14

## 8. Gaps and Recommended Next Requirements
1. Implement explicit swipe/reorder interactions to fully match original interaction vision (FR-17/FR-18).
2. Add direct feature-selection controls during preference narrowing (FR-19).
3. Add named persistent user collections/profiles with auth (FR-20).
4. Define measurable API/UI performance targets and success criteria (NFR-02).
5. Add formal evaluation benchmarks with target thresholds per category.
