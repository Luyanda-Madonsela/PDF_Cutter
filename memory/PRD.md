# PaperCut — SA Past Paper Question Splitter

## Problem
User has ~10,000 South African high school past paper PDFs. They need an app that takes a PDF, uses AI to find where each question starts and stops, crops each question into an image, and returns a ZIP of labelled, ordered images.

## User choices
Gemini 3 Flash (Emergent Universal Key); split down to sub-questions (1.1, 1.2); questions that run across pages stitched into one tall image; one PDF per job, one ZIP each.

## Architecture
- Backend: FastAPI + PyMuPDF. Each page is rendered and sent to Gemini (6 at a time), which returns y-ranges per sub-question (0-1000) plus a CONTINUED marker. Segments are merged across pages, cropped from a 180dpi render, blank space is trimmed, and multi-page parts are stitched together.
- Storage: PDFs and PNGs go to Emergent Object Storage. Jobs are kept in MongoDB (`jobs`), and deletes are soft deletes.
- Endpoints: POST/GET /api/jobs, GET /api/jobs/{id}, /images/{filename}, /zip, DELETE.
- Frontend: single page, dark "technical" theme. Upload, live progress, results grid with a zoom view, ZIP download, history list.

## Implemented (2026-06)
- MVP done end to end and tested (backend 9/9, frontend flows passing)
- Storage calls retry on 5xx errors; page images are cleared from memory once used

## Iteration 2 (2026-06)
- Bulk upload queue: drop many PDFs at once (3 upload at a time); a single background worker processes jobs in order and picks up where it left off after a restart; queue counts, filters and retry for failed jobs
- Smart file naming: AI reads the cover page (subject, grade, year, session, paper, Q-paper vs memo), e.g. Mathematics_Gr12_2024_Nov_P1_001_Q1.1.png; details can be edited and files are renamed
- Crop adjusting: page preview with draggable top/bottom edges, extend onto the next page, rename, merge with next, delete
- Memo matching: memos pair automatically by subject/grade/year/session/paper or can be attached manually; question paper ZIP includes *_MEMO.png next to each question plus memo_unmatched/
- Backend split into core/models/ai/imaging/jobs/routes modules; 18 pytest cases passing

## Iteration 3 (2026-06)
- Crops leave out question totals [16], section totals, paper TOTAL lines and "QUESTION n"/"SECTION X" headings (AI marks their boxes, which are painted white, and segments start below headings)
- Per-question marks = sum of the (n) allocations, editable; merging adds them together
- Meta now includes province (GP/KZN/WC/EC/FS/LP/MP/NW/NC/IEB/National); session standardised to Feb/Mar, May/Jun, Sep, Nov, Exemplar
- Filename: 001_Mathematics_Gr12_2024_Nov_National_P1_Q1.1_7marks.png
- Prompt now makes the AI list every sub-question first, so none are merged or skipped (3 of 3 runs perfect)

## Iteration 4 (2026-06)
- Paper sets: a question paper must come with its memo; optional addenda and errata. Two upload modes in the header menu: One paper (4 slots, QP + memo required) or Bulk (the AI reads each cover and groups files into sets; papers with no memo wait as "Needs memo" and are not split until one is added)
- Two-stage worker: sort covers first, then split; it picks up where it left off after a restart
- Crops erase the sub-question's own number, QUESTION headings and totals using magic erase (fill with the surrounding median colour); the AI flags questions it can't clean safely; "Marks not found" and "No matching memo answer" flags; Mark reviewed
- Images are tight to a shared content column and scaled to exactly 1400px wide
- Errata items are labelled by the question they fix, and addendum figures are linked to their question(s) (a main-question item links to all its sub-questions); the ZIP puts _MEMO/_ADDENDUM/_ERRATA files beside each question, plus addendum_general/, unlinked/, memo_unmatched/
- Storage: PDFs, page previews and crops are all in Emergent Object Storage (already in place since the MVP)
- 23 backend tests passing (iteration_4)

## Backlog
- P1: Combined ZIP download for many papers (e.g. by subject/year)
- P1: Split a single image into two
- P2: Upload size limit; more than one worker for higher throughput
