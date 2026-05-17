# Grasp.Study Course Downloader — Setup & Usage Guide

## What It Does
Automatically logs into your Grasp.Study account, visits every lesson in the
course, and saves each one as a self-contained Markdown file (`.md`) with all
images embedded directly, so you can read them offline — no internet needed.

---

## Folder Structure After Download

```
CourseContent/
├── index.md                                      ← clickable table of contents
├── 01_Data_Structures_Performance_Comparison.md
├── 02_Hash_Map_Collisions_and_Performance.md
├── 03_Balancing_Act_Lookups_vs_Range_Queries.md
└── ...
downloader.log                                    ← log of the run
```

---

## Prerequisites

### 1. Python 3.8 or newer
Check your version:
```bash
python --version
```
Download from https://python.org if needed.

### 2. Google Chrome browser
Make sure Chrome is installed on your machine.  
The script drives Chrome in **headless** mode (no visible window).

### 3. Python packages
```bash
pip install -r requirements.txt
```
This installs Selenium, BeautifulSoup, requests, html2text, Pillow, and
**webdriver-manager** (which automatically downloads the right ChromeDriver
for your Chrome version — no manual setup needed).

---

## Running the Script

```bash
python course_downloader.py
```

That's it. The script will:
1. Open Chrome silently in the background
2. Log in with your credentials
3. Visit the course page and discover all lessons
4. Download each lesson one by one
5. Save everything to `./CourseContent/`
6. Print a summary when done

### Expected output
```
════════════════════════════════════════════════
  Grasp.Study Course Downloader
════════════════════════════════════════════════

[01/24]  Data Structures: Performance Comparison
[02/24]  Hash Map Collisions and Performance
[03/24]  Balancing Act: Lookups vs. Range Queries
...
════════════════════════════════════════════════
  ✅ Done!  24 lesson(s) saved to: /path/to/CourseContent
════════════════════════════════════════════════
```

---

## Reading the Files Offline

Any Markdown viewer will work. Recommended options:
- **VS Code** — install the "Markdown Preview Enhanced" extension, then press
  `Ctrl+Shift+V` to preview
- **Obsidian** (free app) — open the `CourseContent` folder as a vault
- **Typora** — opens `.md` files with a beautiful live preview
- **Any browser** — rename `.md` to `.html` (rough but works)
- **GitHub** — upload the folder to a private repo; GitHub renders markdown natively

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ChromeDriver not found` | `pip install webdriver-manager` (already in requirements) |
| Still on sign-in after login | Double-check credentials in the script |
| 0 lessons found | The page may load differently; open `course_downloader.py`, find `headless=new`, change it to `headless=False` to watch the browser |
| Images missing in .md | Check `downloader.log` for image download errors; may be auth-protected |
| Script too slow | Reduce `PAGE_LOAD_DELAY` in the config section (risk: content may not fully load) |

---

## Changing the Save Location

Edit line ~46 in `course_downloader.py`:

```python
OUTPUT_DIR = "./CourseContent"   # ← change this to any path you like
```

Examples:
```python
OUTPUT_DIR = "/home/yourname/Documents/GraspCourse"
OUTPUT_DIR = "C:/Users/YourName/Desktop/GraspCourse"   # Windows
```

---

## Security Note

Your login credentials are stored in plain text inside the script.
Once you've finished downloading, consider removing them or moving the
script to a private location.
