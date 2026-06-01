# Syndicate System

A research tool for tracking Australian lottery **syndicate** trends across draws.
It documents and analyses number/syndicate patterns over time — it is **not** a
prediction system.

## What it does
- Scrapes public syndicate listings from thelott.com (NSW, VIC, QLD, SA, TAS).
- Splits the data per game (Powerball, Oz Lotto, Saturday Lotto, Set for Life,
  Mon/Wed/Fri).
- Runs a matching engine comparing historical drawn combinations against several
  "variable" sets (Base, Rainbow, Splits, SplitsCombi, ExcelPro, Direct).
- Presents everything in a Streamlit web app.

## Running it
```bash
pip install -r requirements.txt
playwright install chromium      # only needed for the lottolyzer scraper
streamlit run masterapp.py
```
Then open http://localhost:8501 in your browser.

## Project layout
See `PROJECT_SUMMARY.md` for the full folder structure, game-name mapping, and
pipeline notes.

## A note on data
This repository contains **code only**. Scraped data, generated outputs, and large
datasets are intentionally excluded — see `.gitignore`.
