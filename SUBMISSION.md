# Submission package

This file is a checklist for assembling the PDF you'll hand in.

## What goes in the PDF

1. **Cover page** with your name, student ID, module code (ITDS620),
   submission date, and the live URL of the deployed application.
2. **The report** (`REPORT.md`, ~8000 words). Convert via `pandoc`:

   ```bash
   pandoc REPORT.md \
     -o report.pdf \
     --pdf-engine=xelatex \
     --metadata title="Stride — ITDS620 Project Report" \
     --metadata author="Your Name (Student ID)" \
     --metadata date="$(date +%Y-%m-%d)" \
     -V geometry:margin=1in \
     -V mainfont="Helvetica" \
     --toc --toc-depth=2 \
     --highlight-style=tango
   ```

3. **Screenshots** — one per page of the application:
   - Dashboard
   - Tasks list (with the actual-vs-predicted column visible)
   - A task detail with a logged session
   - Subjects list with at least one row
   - Planner showing distributed minutes
   - Insights showing scatter + KPI cards
   - Sign-up page (showing OAuth buttons + password policy text)

   Take them while logged in as the demo user (`demo` / `Demo1234!`).
   Crop to the browser viewport — no OS chrome.

4. **A short "How to evaluate" appendix** with two links:
   - Live URL: `https://<your-username>.pythonanywhere.com/`
   - Source code on GitHub: `https://github.com/<your-username>/stride`

## What stays out of the PDF

- Raw source code. The codebase is ~4000 lines and unreadable in PDF
  form. The GitHub link is what the marker uses to inspect the code.
- The full test suite output. Mention "117 automated tests passing,
  79% coverage" in the report; don't dump the run.

## Recommended PDF assembly

If you don't have LaTeX/pandoc set up:

1. Open `REPORT.md` in any markdown viewer (Typora, Obsidian, even VS
   Code's preview), print to PDF.
2. Add the cover page in Word/Pages and combine.
3. Append the screenshots as a final "Appendix A — Screenshots" section.
4. Submit.

## Pre-submission verification

Before clicking submit:

```bash
# All tests passing
make test

# Lint clean
make lint

# App boots cleanly
flask --app app.py run --debug --port 5050
```

Then visit `http://127.0.0.1:5050/`, log in as `demo` / `Demo1234!`,
and click through every page. Anything that doesn't render or shows an
unexpected error is a regression — fix before submitting.
