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

## Iteration 6 (2026-06): Google sign-in
- Emergent-managed Google sign-in locks the whole app (all /api/* except /api/auth/* need a session cookie or Bearer token). Everyone shares one library.
- backend/auth.py: /api/auth/session, /me, /logout. Collections: users, user_sessions
- Frontend: AuthGate (login screen, callback) and UserMenu in the header
- Tests: auth 14/14, frontend flows pass. 4 older pytest cases fail because a merge/delete test changes the shared seeded set (test data only)

## Drive plan (waiting on the user's OAuth Client ID and Secret)
- Root: My Drive/Fundani Group (Holdings Company)/ResourceWiz Inc/Past Paper Database/CAPS & IEB Past Papers/
- Path: {Year}/Grade {N}/{Subject}/{Session: Feb-Mar|May-Jun|Sept|Nov|Misc}/{Province: DBE|EC|FS|GP|IEB|KZN|LIM|MP|NW|WC}/
  - PDFs go in Paper_N/, Memo_Paper_N/, Addendum/, Errata/ (skip if already there)
  - Images go in Questions/Paper_N/Question_{main no.}/{Question,Memo,Addendum,Errata}/ (Hints/ and Video/ are left alone). Replace files with the same name
  - Catalogues go in CAPS & IEB Past Papers/Catalogues/
- Map National to DBE, LP to LIM, Sep to Sept. Create missing folders
- Upload automatically when a set is finalised, plus a manual "Send to Drive" button. Keep the ZIP
- OAuth redirect: https://papercut-sa.preview.emergentagent.com/api/drive/callback, scope drive

## Backlog
- P0 Google Drive upload (waiting on keys)
- P1 Excel CAPS/IEB check; older sets still have old topic names (e.g. 'Patterns')

## Iteration 7 (2026-06)
- Excel: every block uses the canonical CAPS topic columns (backend/syllabus.py CANON/RENAMES; scripts/normalize_catalogues.py). Question cells use one format: Q1, Q1.2, Q6.1-6.4, Q9(a), '-'. No data was lost. Backups are in /app/memory/catalogues_backup_*
- Rows for exams that were never written are greyed out (fill FFD9D9D9, scripts/grey_catalogues.py): years after 2026, Sept/Nov 2026, May/Jun 2020 (except DBE Gr12), IEB outside Gr12 Nov, DBE Gr12 Sept, DBE Gr12 Feb/Mar from 2018, and DBE Gr7-11 outside Nov. Rows that already hold data are never greyed. locate() refuses greyed rows
- Rules dropped because the user's own data contradicts them: single-paper Gr7-9, and "provincial Feb/Mar doesn't exist" (KZN has Feb/Mar papers)
- Topic Refresh: POST /api/catalogues/refresh-topics plus a button in the catalogues panel
- Manual erase: drag boxes in the Erase tab (always visible). Stored in erase_manual and validated against the crop
- Memo/addendum/errata images can be edited (Erase, Adjust crop) from the question popup. Rename, merge and delete on the question paper are copied to the linked memo (and to addendum/errata images with the same label)
- Answer spaces (lines, boxes, grids) are cut out of question crops (QP prompt answer_spaces plus ai.cut_bands)
- Google Drive (drive.py): one shared OAuth connection (db.drive_credentials _id=shared). Sends automatically when a set is done with no pending erases (once), and has a manual Send/Send again button. Badges show in the set header and queue. Catalogue xlsx goes to <root>/Catalogues
- Tests: iteration_7 is 20/20 new; frontend passes; sync tested by hand on a cloned set. The real Drive upload is untested until the user connects

## Backlog
- P0 User adds the redirect URI in Google Cloud, connects Drive, and checks the first real upload
- P1 Fix the 4 old pytest cases that depend on a seeded set changed by an earlier test
- P2 Let the Drive root path be changed in the UI

## Iterations 8-10 (2026-06)
- Drive main folder can be a pasted Drive folder link (default: Past Paper Database 1Rbo3-EfjwO3mufbN12jU514FPfd9ur2i) plus a sub-folder ("CAPS & IEB Past Papers"). Set in the Drive settings dialog. Paths use "id:<folder>"
- Import from Drive ("From Drive" tab, drive_import.py): search all PDFs by name and import the ticked ones, or scan & import unsplit PDFs (limit 50-1000). Imported jobs keep drive_source, so images go back to the original paper folder and the PDF isn't uploaded again. PDFs the app uploads are tagged appProperties papercut=1 so the scan skips them
- Re-crop: per set, or for all done sets (warning shows how many have manual edits). Afterwards the set re-uploads to Drive
- Undo crop: step-by-step undo inside the editor, plus server-side crop_history (20) and "Restore previous crop" (POST /undo-crop)
- Manual erase boxes can be moved and resized (8 handles)
- Drive OAuth uses login_hint (GOOGLE_DRIVE_ACCOUNT=luyandasmadonselageneral@gmail.com) and prompt=select_account consent
- AI settings (llm.py, header model badge): Emergent / Gemini / OpenAI / Anthropic / OpenRouter / OpenAI-compatible URL, with the user's own key (stored masked). Falls back to the Emergent key when the chosen provider has no key. POST /api/ai/test
- Tests: iteration_8, 9 and 10 all pass

## Blockers / next
- The user must add the redirect URI https://papercut-sa.preview.emergentagent.com/api/drive/callback under "Authorised redirect URIs" (currently empty) and add luyandasmadonselageneral@gmail.com as a test user. Then do the first real Drive upload and import
- P1: fix the 3 old seed-drift pytest cases

## Iteration 11 (2026-06)
- Fixed Drive connect: "invalid_grant Missing code verifier" (PKCE). The connect step now stores flow.code_verifier in drive_states, and the callback restores it
- Cost tracker: db.ai_usage counts per day/provider/model (calls = pages read, tokens in/out); GET /api/ai/usage; editable prices (db.ai_prices, USD per 1M tokens, defaults in llm.DEFAULT_PRICES); "Usage & cost" tab in the AI dialog. Tracking starts 11 Oct 2026
- Tests: iteration_11 100%
