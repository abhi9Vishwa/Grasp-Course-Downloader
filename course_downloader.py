"""
=============================================================
  Grasp.Study Course Downloader  v2.0
  -----------------------------------------------------------
  Downloads every lesson from your enrolled Grasp.Study course
  and saves each one as a self-contained Markdown file with
  images embedded as base64 data URIs (no internet needed).

  Usage:
      python course_downloader.py

  Requirements:
      pip install -r requirements.txt

  Also requires Google Chrome installed.
  ChromeDriver is managed automatically via webdriver-manager.
=============================================================
"""

# Force UTF-8 output on Windows so box-drawing chars / emoji render correctly
import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# --- Standard Library --------------------------------------------------------
import os
import re
import time
import base64
import logging
import traceback
from datetime import datetime
from urllib.parse import urljoin, urlparse

# ─── Third-Party ─────────────────────────────────────────────────────────────
try:
    import requests
    from bs4 import BeautifulSoup
    import html2text
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException,
        NoSuchElementException,
        ElementClickInterceptedException,
        WebDriverException,
        StaleElementReferenceException,
    )
except ImportError as e:
    print(f"\n❌ Missing dependency: {e}")
    print("Run: pip install -r requirements.txt")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION  ← Edit these values before running
# ══════════════════════════════════════════════════════════════════════════════

CREDENTIALS = {
    "email":    "limegi5240@noihse.com",
    "password": "Q1w2e3r4t5y6&",
}

URLS = {
    "login":  "https://paths.grasp.study/sign-in",
    "course": "https://paths.grasp.study/courses/722b2d01-3990-4963-820f-ee0c95fb1cc1",
}

OUTPUT_DIR = "./LinuxInternals"          # Folder where all .md files are saved

# Tuning knobs – increase on slow internet
WAIT_TIMEOUT        = 25    # seconds to wait for elements to appear
PAGE_LOAD_DELAY     = 4     # seconds to let JS settle after navigation
SHOW_MORE_DELAY     = 2     # seconds to wait after clicking "Show More"
IMAGE_DL_RETRIES    = 3     # how many times to retry a failed image download
IMAGE_DL_TIMEOUT    = 15    # seconds per image download request


# ══════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════════════════

os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(OUTPUT_DIR, "downloader.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger("GraspDownloader")


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def slugify(text: str, max_len: int = 80) -> str:
    """Convert arbitrary text to a safe filename segment."""
    text = text.strip()
    text = re.sub(r"[^\w\s-]", "", text)          # remove non-alphanumeric
    text = re.sub(r"[\s_-]+", "_", text)          # spaces/dashes → underscore
    text = re.sub(r"^_+|_+$", "", text)           # strip leading/trailing _
    return text[:max_len] if text else "lesson"


def make_filename(seq: int, title: str) -> str:
    """Return e.g. '03_Hash_Map_Collisions.md'"""
    return f"{seq:02d}_{slugify(title)}.md"


def download_image(url: str, session: requests.Session) -> bytes | None:
    """Download an image, retrying up to IMAGE_DL_RETRIES times."""
    for attempt in range(1, IMAGE_DL_RETRIES + 1):
        try:
            r = session.get(url, timeout=IMAGE_DL_TIMEOUT)
            if r.status_code == 200:
                return r.content
            log.warning(f"    Image HTTP {r.status_code}: {url[:80]}")
        except Exception as exc:
            log.warning(f"    Image download error (attempt {attempt}): {exc}")
        time.sleep(1)
    return None


def guess_mime(url: str) -> str:
    ext = urlparse(url).path.rsplit(".", 1)[-1].lower().split("?")[0]
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png",  "gif": "image/gif",
        "svg": "image/svg+xml", "webp": "image/webp",
        "bmp": "image/bmp",
    }.get(ext, "image/png")


# ══════════════════════════════════════════════════════════════════════════════
#  SELENIUM SETUP
# ══════════════════════════════════════════════════════════════════════════════

def build_driver(headless: bool = True) -> webdriver.Chrome:
    """Build a Chrome driver. Falls back to webdriver-manager if chromedriver
    is not on PATH."""
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--log-level=3")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # ── Try plain chromedriver first ────────────────────────────────────────
    try:
        driver = webdriver.Chrome(options=opts)
        log.info("ChromeDriver found on PATH ✓")
        return driver
    except WebDriverException:
        pass

    # ── Fall back to webdriver-manager ──────────────────────────────────────
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
        log.info("ChromeDriver installed via webdriver-manager ✓")
        return driver
    except ImportError:
        print(
            "\n❌ ChromeDriver not found and 'webdriver-manager' is not installed.\n"
            "Fix: pip install webdriver-manager\n"
            "  or download ChromeDriver manually from https://chromedriver.chromium.org/downloads"
        )
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Could not start Chrome: {e}\nMake sure Google Chrome is installed.")
        sys.exit(1)


def wait_for(driver, by, selector, timeout=WAIT_TIMEOUT):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )


def wait_clickable(driver, by, selector, timeout=WAIT_TIMEOUT):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, selector))
    )


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 1 – AUTHENTICATION
# ══════════════════════════════════════════════════════════════════════════════

def login(driver: webdriver.Chrome) -> bool:
    """Authenticate with email + password. Returns True on success.
    
    Grasp.Study uses:
      - input[placeholder='Username / Email']  for the email field
      - input[type='password']                 for the password field
      - A button with text 'Continue'          to submit
    Login success = redirected away from /sign-in (typically to /home)
    """
    log.info("Navigating to login page …")
    driver.get(URLS["login"])
    time.sleep(PAGE_LOAD_DELAY)

    try:
        # ── Fill email ───────────────────────────────────────────────────────
        log.info("  Filling email …")
        email_field = wait_for(
            driver, By.CSS_SELECTOR,
            "input[placeholder='Username / Email'], "
            "input[type='email'], input[name='email'], input[id*='email' i]"
        )
        email_field.clear()
        email_field.send_keys(CREDENTIALS["email"])
        time.sleep(0.5)

        # ── Fill password ────────────────────────────────────────────────────
        log.info("  Filling password …")
        pw_field = driver.find_element(
            By.CSS_SELECTOR,
            "input[type='password'], input[name='password'], input[id*='password' i]"
        )
        pw_field.clear()
        pw_field.send_keys(CREDENTIALS["password"])
        time.sleep(0.5)

        # ── Submit ────────────────────────────────────────────────────────────
        # Grasp.Study has TWO buttons with 'Continue' in text:
        #   1. "Continue with Google" – the OAuth button (must AVOID)
        #   2. The green email-form submit button below the OR separator
        # We target the submit button inside the <form> element only.
        log.info("  Clicking Continue (email form submit) ...")
        try:
            # Most reliable: the submit button inside the password form
            submit = wait_clickable(
                driver, By.XPATH,
                "//form//button[@type='submit' or "
                "(not(contains(normalize-space(.), 'Google')) "
                "and contains(normalize-space(.), 'Continue'))]",
                timeout=10
            )
        except TimeoutException:
            # Fallback: any button that is NOT the Google one
            btns = driver.find_elements(By.CSS_SELECTOR, "button")
            submit = next(
                (b for b in btns
                 if "google" not in b.text.lower()
                 and "continue" in b.text.lower()
                 and b.is_displayed()),
                None
            )
            if not submit:
                submit = driver.find_element(By.CSS_SELECTOR,
                                             "form button[type='submit'], "
                                             "form button:last-of-type")
        submit.click()

        # ── Wait for redirect to dashboard ───────────────────────────────────
        log.info("  Waiting for redirect …")
        time.sleep(PAGE_LOAD_DELAY + 3)

        current = driver.current_url
        if "sign-in" in current or "login" in current:
            # Try once more – maybe a slow redirect
            time.sleep(3)
            current = driver.current_url

        if "sign-in" in current or "login" in current:
            log.error(f"Still on sign-in page after login! URL: {current}")
            log.error("Check credentials or network connection.")
            return False

        log.info(f"  Login successful ✓  (now at {current})")
        return True

    except Exception as exc:
        log.error(f"Login failed: {exc}")
        log.debug(traceback.format_exc())
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 2 – LESSON DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

def expand_all_modules(driver: webdriver.Chrome) -> None:
    """Click every per-module 'Show More' button until none remain.

    Grasp shows only ~5 lessons per module by default; each module has its
    own 'Show More' button. We click ALL visible ones per pass, then repeat
    until the page has no more expandable sections.
    """
    log.info("  Expanding all modules (clicking 'Show More' buttons) ...")
    clicks = 0
    for _round in range(30):  # safety cap
        btns = driver.find_elements(
            By.XPATH,
            "//button[contains(translate(normalize-space(.), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
            "'show more')]"
        )
        visible = [b for b in btns if b.is_displayed() and b.is_enabled()]
        if not visible:
            break

        for btn in visible:
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(0.4)
                try:
                    btn.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", btn)
                clicks += 1
                log.info(f"    Clicked 'Show More' #{clicks}")
                time.sleep(SHOW_MORE_DELAY)
            except StaleElementReferenceException:
                pass  # button vanished after click – that's fine

    log.info(f"  Done expanding ({clicks} Show More click(s)).")


def extract_lesson_links(driver: webdriver.Chrome) -> list[dict]:
    """
    Return ordered list of { "title": str, "url": str } from the course page.
    Lesson links on Grasp follow: /courses/.../modules/.../lessons/...
    """
    log.info("Navigating to course page …")
    driver.get(URLS["course"])
    time.sleep(PAGE_LOAD_DELAY)

    # Expand collapsed module sections
    expand_all_modules(driver)
    time.sleep(1)

    soup = BeautifulSoup(driver.page_source, "lxml")
    parsed = urlparse(driver.current_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    lessons  = []
    seen_urls = set()

    # Grasp lesson URLs always contain /lessons/
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "/lessons/" not in href:
            continue
        full_url = href if href.startswith("http") else urljoin(base, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        # Best title: visible text → aria-label → title attr → generic
        title = a.get_text(separator=" ", strip=True)
        if len(title) < 3:
            title = (a.get("aria-label") or a.get("title") or
                     f"Lesson {len(lessons) + 1}")

        # Clean up common noise text
        title = re.sub(r"\s+", " ", title).strip()
        lessons.append({"title": title, "url": full_url})

    log.info(f"Found {len(lessons)} lesson(s) on course page.")
    return lessons


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 3 – CONTENT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def scroll_to_bottom(driver: webdriver.Chrome) -> None:
    """Scroll gradually to trigger lazy-loading of images and content."""
    total = driver.execute_script("return document.body.scrollHeight")
    step  = 600
    pos   = 0
    while pos < total:
        pos += step
        driver.execute_script(f"window.scrollTo(0, {pos});")
        time.sleep(0.25)
        # Re-check in case page grew after scroll
        total = driver.execute_script("return document.body.scrollHeight")
    driver.execute_script("window.scrollTo(0, 0);")


# Content container selectors, tried in priority order
CONTENT_SELECTORS = [
    "article",
    "[class*='lesson-content']",
    "[class*='LessonContent']",
    "[class*='prose']",
    "main [class*='content']",
    "[class*='markdown']",
    "main article",
    "main",
    "[role='main']",
    "[class*='post-body']",
    "[class*='body-content']",
]

# Elements to strip from the content container
NOISE_SELECTORS = (
    "nav, header, footer, script, style, "
    "[class*='nav'], [class*='sidebar'], [class*='toolbar'], "
    "[class*='share'], [class*='done-button'], [class*='progress'], "
    "[class*='breadcrumb'], [class*='pagination'], [class*='comment'], "
    "button, [role='navigation'], [role='complementary']"
)


def extract_lesson_content(driver: webdriver.Chrome,
                            lesson: dict,
                            session: requests.Session) -> dict:
    """
    Navigate to a lesson page and extract:
        title, outcome text, body HTML, base URL
    """
    log.info(f"  → Fetching: {lesson['title'][:70]}")
    driver.get(lesson["url"])
    time.sleep(PAGE_LOAD_DELAY)

    # Wait for meaningful content
    for selector in ["h1", "h2", "[class*='content']", "main"]:
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            break
        except TimeoutException:
            continue

    scroll_to_bottom(driver)
    time.sleep(1)

    soup     = BeautifulSoup(driver.page_source, "lxml")
    base_url = driver.current_url

    # ── Title ────────────────────────────────────────────────────────────────
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else lesson["title"]

    # ── Lesson Outcome ───────────────────────────────────────────────────────
    outcome = ""
    for candidate in soup.find_all(string=re.compile(r"lesson\s+outcome", re.I)):
        parent = candidate.find_parent()
        if parent:
            sib = parent.find_next_sibling()
            if sib:
                outcome = sib.get_text(" ", strip=True)
            if not outcome:
                nxt = parent.find_next("p")
                if nxt:
                    outcome = nxt.get_text(" ", strip=True)
            if outcome:
                break

    # ── Main body ─────────────────────────────────────────────────────────────
    body_html = ""
    for sel in CONTENT_SELECTORS:
        node = soup.select_one(sel)
        if node and len(node.get_text(strip=True)) > 100:
            # Strip navigation chrome from inside the container
            for trash in node.select(NOISE_SELECTORS):
                trash.decompose()
            body_html = str(node)
            log.debug(f"    Content captured via selector: {sel}")
            break

    # Fallback: use full body minus nav/header/footer
    if not body_html:
        log.warning("    No content container found – falling back to full body")
        body = soup.find("body")
        if body:
            for trash in body.select("nav, header, footer, script, style"):
                trash.decompose()
            body_html = str(body)

    return {
        "title":    title,
        "outcome":  outcome,
        "html":     body_html,
        "base_url": base_url,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE EMBEDDING
# ══════════════════════════════════════════════════════════════════════════════

def embed_images(html: str, base_url: str, session: requests.Session) -> str:
    """
    Replace every <img src="..."> with a base64 data URI so the markdown
    file is fully self-contained and viewable offline.
    """
    soup = BeautifulSoup(html, "lxml")
    imgs = soup.find_all("img")
    log.info(f"    Embedding {len(imgs)} image(s) …")

    for img in imgs:
        # Try src, then data-src (lazy-load), then data-original
        src = (img.get("src") or img.get("data-src") or
               img.get("data-original") or img.get("data-lazy-src") or "")

        if not src:
            img.decompose()
            continue
        if src.startswith("data:"):      # already base64-embedded
            continue
        if any(s in src for s in ["1x1", "pixel", "blank.gif", "spacer"]):
            img.decompose()
            continue

        abs_url = src if src.startswith("http") else urljoin(base_url, src)
        mime    = guess_mime(abs_url)

        img_bytes = download_image(abs_url, session)
        if img_bytes:
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            img["src"] = f"data:{mime};base64,{b64}"
            img.attrs.pop("srcset", None)     # remove responsive hints
            img.attrs.pop("data-src", None)
            log.debug(f"      ✓ embedded {abs_url[:70]}")
        else:
            log.warning(f"      ✗ could not download {abs_url[:80]}")

    return str(soup)


# ══════════════════════════════════════════════════════════════════════════════
#  HTML → MARKDOWN
# ══════════════════════════════════════════════════════════════════════════════

def html_to_markdown(html: str) -> str:
    """Convert HTML to clean Markdown, preserving base64 image data URIs."""
    h = html2text.HTML2Text()
    h.ignore_links      = False
    h.ignore_images     = False
    h.body_width        = 0         # no line wrapping
    h.protect_links     = True
    h.unicode_snob      = True
    h.ignore_emphasis   = False
    h.single_line_break = False
    h.images_to_alt     = False

    return h.handle(html)


# ══════════════════════════════════════════════════════════════════════════════
#  MARKDOWN FILE WRITER
# ══════════════════════════════════════════════════════════════════════════════

def save_markdown(seq: int, lesson_data: dict, source_url: str) -> str:
    """Write one lesson to disk as a Markdown file. Returns the saved filepath."""
    title    = lesson_data["title"]
    outcome  = lesson_data["outcome"]
    html     = lesson_data["html"]
    base_url = lesson_data["base_url"]

    filename = make_filename(seq, title)
    filepath = os.path.join(OUTPUT_DIR, filename)

    lines = []
    lines.append(f"# {title}\n")
    lines.append(f"> **Source:** {source_url}  ")
    lines.append(f"> **Downloaded:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    if outcome:
        lines.append("\n---\n")
        lines.append("## 🎯 Lesson Outcome\n")
        lines.append(f"{outcome}\n")

    lines.append("\n---\n")
    lines.append("## 📖 Content\n")

    # Embed images into HTML, then convert to Markdown
    session           = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    html_with_images  = embed_images(html, base_url, session)
    body_md           = html_to_markdown(html_with_images)
    lines.append(body_md)

    full_md = "\n".join(lines)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_md)

    size_kb = os.path.getsize(filepath) / 1024
    log.info(f"    ✅ Saved: {filename}  ({size_kb:.1f} KB)")
    return filepath


# ══════════════════════════════════════════════════════════════════════════════
#  INDEX FILE
# ══════════════════════════════════════════════════════════════════════════════

def create_index(lessons_meta: list[dict]) -> None:
    """Generate a master index.md file linking to every lesson."""
    path = os.path.join(OUTPUT_DIR, "index.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 📚 Grasp.Study — Offline Course Index\n\n")
        f.write(f"**Course URL:** {URLS['course']}  \n")
        f.write(f"**Downloaded:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n")
        f.write(f"**Total lessons:** {len(lessons_meta)}  \n\n")
        f.write("---\n\n")
        f.write("## Table of Contents\n\n")
        for m in lessons_meta:
            f.write(f"{m['seq']:2d}. [{m['title']}](./{m['filename']})\n")
    log.info(f"📄 Index created: {path}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("\n" + "=" * 62)
    print("  Grasp.Study Course Downloader  v2.0")
    print("=" * 62 + "\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    driver  = build_driver(headless=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    lessons_meta: list[dict] = []

    try:
        # ── Phase 1: Login ───────────────────────────────────────────────────
        print("🔐 Logging in …")
        if not login(driver):
            print("\n❌ Could not log in. Exiting.")
            return

        # Transfer Selenium session cookies → requests.Session
        # so images behind authentication can be downloaded.
        for cookie in driver.get_cookies():
            session.cookies.set(
                cookie["name"], cookie["value"],
                domain=cookie.get("domain", "")
            )

        # ── Phase 2: Discover lessons ─────────────────────────────────────────
        print("\n🔍 Discovering lessons …")
        lessons = extract_lesson_links(driver)

        if not lessons:
            log.error("No lessons found! The course page structure may have changed.")
            log.error("Try setting headless=False in build_driver() to debug.")
            return

        print(f"\n[INFO] {len(lessons)} lessons found. Starting download...\n")

        # ── Phase 3: Download each lesson ─────────────────────────────────────
        failed = []

        for seq, lesson in enumerate(lessons, start=1):
            print(f"[{seq:02d}/{len(lessons):02d}]  {lesson['title'][:70]}")
            try:
                content  = extract_lesson_content(driver, lesson, session)
                filepath = save_markdown(seq, content, lesson["url"])

                lessons_meta.append({
                    "seq":      seq,
                    "title":    content["title"],
                    "filename": os.path.basename(filepath),
                })

            except Exception as exc:
                log.error(f"    ✗ Failed lesson {seq}: {exc}")
                log.debug(traceback.format_exc())
                failed.append(lesson["title"])

            time.sleep(1)   # polite pause between lessons

        # ── Phase 4: Create index ─────────────────────────────────────────────
        if lessons_meta:
            create_index(lessons_meta)

        # ── Summary ───────────────────────────────────────────────────────────
        print("\n" + "=" * 62)
        print(f"  DONE!  {len(lessons_meta)} lesson(s) saved to:")
        print(f"  {os.path.abspath(OUTPUT_DIR)}")
        if failed:
            print(f"\n  WARNING: {len(failed)} lesson(s) failed:")
            for title in failed:
                print(f"    - {title}")
        print("=" * 62 + "\n")

    finally:
        driver.quit()
        log.info("Browser closed.")


if __name__ == "__main__":
    main()
