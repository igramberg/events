# Tasks

This document tracks the program-level work for the `events` app.

Each task should have its own design discussion, written implementation plan, test plan, and exit review before the next task starts.

## Task Summary

| Task | Title | Status | Depends On |
| --- | --- | --- | --- |
| T1 | Repo bootstrap and program design | Complete | None |
| T2 | Core event model and inclusion rules | Not started | T1 |
| T3 | Source adapter framework and generic parser | Not started | T2 |
| T4 | Storage layer for current-week events | Not started | T2 |
| T5 | Web UI shell and weekly list page | Not started | T2, T4 |
| T6 | V0 source pack for music and theater | Not started | T3, T4, T5 |
| T7 | Manual refresh flow | Not started | T3, T4, T5, T6 |
| T8 | Scheduler | Not started | T7 |
| T9 | Phase 2 source packs for exhibitions, museum nights, and film | Not started | T3, T4, T5, T7 |

## Task Template

Each task should be worked in this format:

| Field | Description |
| --- | --- |
| Objective | What the task is meant to achieve |
| Scope | What is included and excluded |
| Design Questions | Open decisions to resolve before coding |
| Implementation Plan | Ordered steps for the task |
| Test Plan | Tests that will be written first and how they will be verified |
| Exit Criteria | What must be true before the task is complete |

## Task Details

### T1. Repo Bootstrap and Program Design

| Field | Detail |
| --- | --- |
| Objective | Create the repository, record the architecture, and scaffold the minimal project structure |
| Scope | Repo initialization, project metadata, architecture docs, FastAPI bootstrap skeleton, bootstrap test |
| Design Questions | Repo location, baseline stack, V0 scope boundaries |
| Implementation Plan | Create `~/src/events`, initialize git, write docs, scaffold project, add bootstrap test |
| Test Plan | Verify the app bootstrap can be imported and created |
| Exit Criteria | Repo exists, docs exist, app skeleton exists, bootstrap test passes |

### T2. Core Event Model and Inclusion Rules

| Field | Detail |
| --- | --- |
| Objective | Define the normalized event model and codify V0 inclusion rules |
| Scope | Domain types, category definitions, date/window rules, inclusion/exclusion criteria |
| Design Questions | Required event fields, category enum design, how to represent city and venue, how strict V0 inclusion rules should be |
| Implementation Plan | Write task design notes, add failing tests for event model and inclusion logic, implement minimal domain layer |
| Test Plan | Model validation tests, category tests, current-week window tests, inclusion rule tests |
| Exit Criteria | Domain model is stable enough for source and storage tasks to build on |

### T3. Source Adapter Framework and Generic Parser

| Field | Detail |
| --- | --- |
| Objective | Create the source adapter contract and a generic structured-data parser |
| Scope | Adapter interface, fetch/parse pipeline shape, generic JSON-LD extraction, normalized parse output |
| Design Questions | Adapter abstraction, parse result format, fetch responsibilities, failure reporting shape |
| Implementation Plan | Define interfaces, write parser tests first, implement generic extraction, keep source-specific logic out of scope |
| Test Plan | Parsing tests for JSON-LD and structured event payloads, adapter contract tests |
| Exit Criteria | The app can parse machine-readable event data from a source page into normalized domain events |

### T4. Storage Layer for Current-Week Events

| Field | Detail |
| --- | --- |
| Objective | Persist normalized events for the current week and prune stale data |
| Scope | SQLite schema, repository layer, upsert behavior, current-week pruning |
| Design Questions | Schema shape, dedupe key, timestamp handling, repository interface |
| Implementation Plan | Design schema, write failing repository tests, implement storage and pruning behavior |
| Test Plan | Upsert tests, read tests, prune tests, duplicate handling tests |
| Exit Criteria | The app can store and query the current week's events reliably |

### T5. Web UI Shell and Weekly List Page

| Field | Detail |
| --- | --- |
| Objective | Provide the first usable local web page for browsing weekly events |
| Scope | FastAPI route, template rendering, weekly list layout, category labels, refresh status placeholder |
| Design Questions | Route shape, page layout, filter strategy for V0, what metadata to show initially |
| Implementation Plan | Design page structure, write route/template tests, implement minimal HTML rendering |
| Test Plan | Route response tests, rendered content tests, empty-state tests |
| Exit Criteria | A user can open the local app and see a weekly events page |

### T6. V0 Source Pack for Music and Theater

| Field | Detail |
| --- | --- |
| Objective | Add the first 4-6 reliable greater-Boston sources for concerts and theater |
| Scope | Source selection, adapter implementations, normalization mapping for chosen sources |
| Design Questions | Which venues to include first, how to handle heterogeneous markup, what to do with partial data |
| Implementation Plan | Select sources, create source-specific tests and fixtures, implement the minimum adapters needed |
| Test Plan | Fixture-based parser tests per source, normalization tests, category mapping tests |
| Exit Criteria | Manual refresh can pull usable events from the initial venue/theater set |

### T7. Manual Refresh Flow

| Field | Detail |
| --- | --- |
| Objective | Let the user trigger a refresh and see updated current-week results |
| Scope | Refresh action, orchestration across sources, storage update, status reporting in the UI |
| Design Questions | Trigger mechanism, sync vs async behavior, user-visible failure handling |
| Implementation Plan | Write end-to-end refresh tests, implement refresh service, connect refresh action to web layer |
| Test Plan | Refresh orchestration tests, failure-path tests, UI status tests |
| Exit Criteria | The user can manually refresh and get updated weekly events in the UI |

### T8. Scheduler

| Field | Detail |
| --- | --- |
| Objective | Add automatic recurring refresh after V0 |
| Scope | Scheduled refresh job, startup/shutdown wiring, basic visibility into refresh success or failure |
| Design Questions | Scheduler library, daily cadence, overlap protection, failure reporting |
| Implementation Plan | Write scheduler behavior tests where practical, implement recurring refresh, expose status in UI |
| Test Plan | Scheduler wiring tests, orchestration call tests, status update tests |
| Exit Criteria | The app refreshes automatically on a schedule without user action |

### T9. Phase 2 Source Packs for Exhibitions, Museum Nights, and Film

| Field | Detail |
| --- | --- |
| Objective | Expand the source catalog beyond V0 categories |
| Scope | New source packs for deferred categories, category-specific inclusion logic, UI support where needed |
| Design Questions | Category boundaries, source reliability, whether new metadata fields are required |
| Implementation Plan | Split by source pack, design each pack separately, add category-specific tests before implementation |
| Test Plan | Source-pack parser tests, category inclusion tests, UI/category rendering tests |
| Exit Criteria | Deferred categories are supported without destabilizing V0 behavior |
