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

## Backlog
- P0: Batch/bulk upload with a queue (for 10k PDFs), plus a combined ZIP
- P1: Manual re-crop/adjust boundaries; matching memo (answer) PDFs to question images
- P1: Metadata in filenames (subject, grade, year, paper)
- P2: Upload size limit; resume jobs after a restart
