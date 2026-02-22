"""
Automated CS2 Match Scraper (csstats.gg).
Iterates through up to 22 matches, extracts round-level data and scoreboard, saves to CSV.

Note: The site may require login to view player stats. Run Chrome with Selenium;
you can log in manually when the browser opens, then the script continues.
"""

import re
import time
import csv
from typing import List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException


#configuration
START_URL = "https://csstats.gg/player/76561198812851717#/matches"
MAX_MATCHES = 22
SLEEP_BETWEEN_MATCHES = 3
OUTPUT_CSV = "cs2_round_data.csv"
FINAL_OUTPUT_CSV = "cs2_final_clean_data.csv"

#only these tabs are scraped (Scoreboard first when entering match, then Rounds)
MATCH_TABS_TO_SCRAPE = ["Scoreboard", "Rounds"]
OUTPUT_DIR = "."  #directory for CSVs

#selectors for Rounds tab and round cards (site uses "Round 1", not "ROUND 1")
ROUND_CARD_HEADER_PATTERN = "Round "
#left panel: label in center, T value left, CT value right
EQUIPMENT_VALUE_LABEL = "Equipment Value"
CASH_LABEL = "Cash"
CASH_SPENT_LABEL = "Cash Spent"
TERRORISTS_WIN_TEXT = "Terrorists Win"
COUNTER_TERRORISTS_WIN_TEXT = "Counter-Terrorists Win"
# Kill feed: first entry has span.team-ct (blue/CT) or span.team-t (yellow/T) for killer


def _parse_dollar_value(text: Optional[str]) -> Optional[int]:
    """Convert '$16,100' or '$ 16,100' to integer 16100."""
    if not text or not str(text).strip():
        return None
    s = str(text).strip().replace("$", "").replace(",", "").strip()
    if not s or not s.isdigit():
        return None
    return int(s)


def create_driver(headless: bool = False) -> webdriver.Chrome:
    """Create Chrome WebDriver with optional headless mode."""
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=opts)


def _click_match_tab(driver: webdriver.Chrome, tab_name: str) -> bool:
    """Click the tab with text (e.g. 'Scoreboard', 'Rounds'). Returns True if clicked."""
    try:
        wait = WebDriverWait(driver, 8)
        tab = wait.until(
            EC.element_to_be_clickable((By.XPATH, f"//*[contains(normalize-space(.), '{tab_name}') and (self::a or self::button or self::div or self::span)]"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
        time.sleep(0.3)
        tab.click()
        time.sleep(1.5)
        return True
    except (TimeoutException, NoSuchElementException):
        return False


def _click_rounds_tab(driver: webdriver.Chrome) -> bool:
    """
    Switch to Rounds tab. Site uses content_tab('rounds'); tab is <li id="rounds-nav"><span>Rounds</span></li>.
    """
    # Do this first: site's JS switches the content panel reliably
    try:
        driver.execute_script("if (typeof content_tab === 'function') { content_tab('rounds'); }")
        time.sleep(1.2)
        # Verify we have Rounds content (match-rounds visible or round-info-1 present)
        driver.find_element(By.CSS_SELECTOR, "#match-rounds, [id^='round-info-']")
        return True
    except Exception:
        pass
    wait = WebDriverWait(driver, 10)
    for how, value in [
        (By.ID, "rounds-nav"),
        (By.XPATH, "//li[.//span[contains(.,'Rounds')]]"),
        (By.XPATH, "//*[contains(.,'Rounds') and (self::a or self::button or self::li or self::span)]"),
    ]:
        try:
            tab = wait.until(EC.presence_of_element_located((how, value)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", tab)
            time.sleep(1.2)
            return True
        except (TimeoutException, NoSuchElementException):
            continue
    return False


def _wait_for_round_cards(driver: webdriver.Chrome, timeout: int = 15) -> None:
    """Wait for Rounds content: match-rounds or round-info-1; site text is 'Round 1' not 'ROUND 1'."""
    wait = WebDriverWait(driver, timeout)
    try:
        wait.until(EC.visibility_of_element_located((By.ID, "match-rounds")))
    except TimeoutException:
        pass
    # Site uses "Round 1", "Round 2" (capital R only)
    wait.until(
        EC.presence_of_element_located((
            By.XPATH,
            "//*[contains(., 'Round 1') or @id='round-info-1' or contains(@class,'round-info')]"
        ))
    )


def _scrape_tables_on_page(driver: webdriver.Chrome) -> List[dict]:
    """Scrape all visible tables: first row as headers, each following row as a dict. Returns list of rows from all tables."""
    rows: List[dict] = []
    try:
        tables = driver.find_elements(By.TAG_NAME, "table")
        for table in tables:
            try:
                header_cells = table.find_elements(By.XPATH, ".//thead//th | .//tr[1]/th | .//tr[1]/td")
                if not header_cells:
                    continue
                headers = [th.text.strip() or f"col_{i}" for i, th in enumerate(header_cells)]
                data_rows = table.find_elements(By.XPATH, ".//tbody//tr | .//tr[position()>1]")
                for tr in data_rows:
                    cells = tr.find_elements(By.XPATH, ".//td | .//th")
                    if len(cells) < len(headers) and len(cells) > 0:
                        headers_use = [f"col_{i}" for i in range(len(cells))]
                    else:
                        headers_use = headers[: len(cells)]
                    row = {headers_use[i]: (cells[i].text.strip() if i < len(cells) else "") for i in range(len(headers_use))}
                    if any(row.values()):
                        rows.append(row)
            except Exception:
                continue
    except Exception:
        pass
    return rows


def _scrape_tab_content_as_rows(driver: webdriver.Chrome) -> List[dict]:
    """When tab has no table: get main content text and return as one row with 'content' key."""
    try:
        main = driver.find_element(By.XPATH, "//main | //article | //*[contains(@class,'content') or contains(@class,'panel')]")
        text = main.text.strip()
        if text:
            return [{"content": text[:50000]}]
    except NoSuchElementException:
        pass
    return []


def get_map_from_match_page(driver: webdriver.Chrome) -> Optional[str]:
    """Get map name (e.g. de_mirage) from match header on Scoreboard / match page."""
    try:
        # Map often shown near match header with icon or "de_"
        for el in driver.find_elements(By.XPATH, "//*[contains(., 'de_')]"):
            text = (el.text or "").strip()
            if text and re.match(r"de_[a-z0-9_]+", text, re.I):
                return text.split()[0] if text else None
        page_text = driver.find_element(By.TAG_NAME, "body").text
        m = re.search(r"\b(de_[a-z0-9_]+)\b", page_text, re.I)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _get_economic_row(container, label: str) -> Tuple[Optional[int], Optional[int]]:
    """
    In the round card: find the row with this label (Equipment Value, Cash, or Cash Spent).
    Left value = T-side, right value = CT-side. Parse '$3,450' -> 3450 via .replace('$','').replace(',','').
    Returns (value_t, value_ct).
    """
    try:
        label_el = container.find_element(By.XPATH, f".//*[contains(normalize-space(.), '{label}')]")
    except NoSuchElementException:
        return None, None
    # Prefer a tight parent that has only this row (so we don't mix with other rows' $ values)
    for _ in range(5):
        try:
            parent = label_el.find_element(By.XPATH, "./parent::*")
        except NoSuchElementException:
            break
        label_el = parent
        row_text = parent.text or ""
        dollar_matches = re.findall(r"\$[\d,]+", row_text)
        if len(dollar_matches) >= 2:
            return _parse_dollar_value(dollar_matches[0]), _parse_dollar_value(dollar_matches[1])
        if len(dollar_matches) == 1:
            return _parse_dollar_value(dollar_matches[0]), None
    # Fallback: whole container text for this label's row
    try:
        label_el = container.find_element(By.XPATH, f".//*[contains(., '{label}')]")
        grand = label_el.find_element(By.XPATH, "./ancestor::*[contains(@class,'row') or contains(@class,'round-info-side') or self::tr][1]")
        row_text = grand.text or ""
    except NoSuchElementException:
        row_text = container.text or ""
    dollar_matches = re.findall(r"\$[\d,]+", row_text)
    if len(dollar_matches) >= 2:
        return _parse_dollar_value(dollar_matches[0]), _parse_dollar_value(dollar_matches[1])
    if len(dollar_matches) == 1:
        return _parse_dollar_value(dollar_matches[0]), None
    return None, None


def _get_equipment_values_from_row(container) -> Tuple[Optional[int], Optional[int]]:
    """Equipment Value: left = T, right = CT (integer)."""
    return _get_economic_row(container, EQUIPMENT_VALUE_LABEL)


def _get_first_kill_side_from_kill_feed(round_card) -> Optional[str]:
    """
    Kill feed: first entry = first kill. HTML uses span.team-ct (blue/CT) and span.team-t (yellow/T).
    First span with class team-ct or team-t in the first kill entry = killer's side.
    """
    try:
        first_entry = round_card.find_element(By.CSS_SELECTOR, ".tl-inner")
    except NoSuchElementException:
        try:
            entries = round_card.find_elements(By.CSS_SELECTOR, "[class*='tl-inner'], [class*='kill'], [class*='feed'] .tl-inner")
            if not entries:
                return None
            first_entry = entries[0]
        except NoSuchElementException:
            return None
    try:
        team_spans = first_entry.find_elements(By.CSS_SELECTOR, "span.team-ct, span.team-t")
        if not team_spans:
            return None
        first_span = team_spans[0]
        cls = (first_span.get_attribute("class") or "").lower()
        if "team-ct" in cls:
            return "CT"
        if "team-t" in cls:
            return "T"
    except NoSuchElementException:
        pass
    return None


def _get_round_winner_from_card(round_card) -> Optional[str]:
    """Locate 'Terrorists Win' or 'Counter-Terrorists Win' at bottom of round card."""
    text = round_card.text
    if COUNTER_TERRORISTS_WIN_TEXT.lower() in text.lower() or "counter-terrorists win" in text.lower():
        return "CT"
    if TERRORISTS_WIN_TEXT.lower() in text.lower() or "terrorists win" in text.lower():
        return "T"
    return None


def scrape_rounds_from_page(driver: webdriver.Chrome, map_name: Optional[str] = None) -> List[dict]:
    """
    Click ROUNDS tab. Each round card is collapsed by default — click to expand, then scrape.
    Extract: round number, map, equipment value (T/CT), cash, cash spent, first kill (via .team-ct/.team-t), round winner.
    """
    if not _click_rounds_tab(driver):
        print("    Rounds tab not found or not clickable — skipping rounds for this match.")
        return []
    try:
        _wait_for_round_cards(driver)
    except TimeoutException:
        print("    Rounds content did not load (timeout) — skipping rounds.")
        return []
    time.sleep(1)

    rounds_data: List[dict] = []
    max_rounds = 30

    def _scrape_one_card(container) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int], Optional[int], Optional[str], Optional[str]]:
        """Parse one round card element; returns (eq_t, eq_ct, cash_t, cash_ct, spent_t, spent_ct, first_kill, round_winner)."""
        full_text = (container.text or "").strip()
        dollar_matches = re.findall(r"\$[\d,]+", full_text)
        if len(dollar_matches) >= 6:
            eq_t, eq_ct = _parse_dollar_value(dollar_matches[0]), _parse_dollar_value(dollar_matches[1])
            cash_t, cash_ct = _parse_dollar_value(dollar_matches[2]), _parse_dollar_value(dollar_matches[3])
            spent_t, spent_ct = _parse_dollar_value(dollar_matches[4]), _parse_dollar_value(dollar_matches[5])
        else:
            eq_t, eq_ct = _get_equipment_values_from_row(container)
            cash_t, cash_ct = _get_economic_row(container, CASH_LABEL)
            spent_t, spent_ct = _get_economic_row(container, CASH_SPENT_LABEL)
            if (eq_t, eq_ct) == (None, None) and len(dollar_matches) >= 2:
                eq_t, eq_ct = _parse_dollar_value(dollar_matches[0]), _parse_dollar_value(dollar_matches[1])
        first_kill = _get_first_kill_side_from_kill_feed(container)
        round_winner = _get_round_winner_from_card(container)
        return eq_t, eq_ct, cash_t, cash_ct, spent_t, spent_ct, first_kill, round_winner

    for round_num in range(1, max_rounds + 1):
        try:
            card_container = driver.find_element(By.ID, f"round-info-{round_num}")
        except NoSuchElementException:
            break

        # Always expand THIS round's card first (site keeps only one expanded; otherwise we read round 1 for all)
        try:
            round_outer = driver.find_element(
                By.XPATH,
                f"//div[@id='round-info-{round_num}']/preceding-sibling::div[1]//div[contains(@class,'round-outer')]"
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", round_outer)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", round_outer)
            time.sleep(0.6)
        except NoSuchElementException:
            try:
                driver.execute_script("if (typeof round_tab === 'function') round_tab(arguments[0]);", round_num)
                time.sleep(0.6)
            except Exception:
                pass

        try:
            card_container = driver.find_element(By.ID, f"round-info-{round_num}")
        except NoSuchElementException:
            break

        eq_t, eq_ct, cash_t, cash_ct, spent_t, spent_ct, first_kill, round_winner = _scrape_one_card(card_container)
        has_data = (eq_t is not None or eq_ct is not None or round_winner is not None)
        if not has_data:
            break

        rounds_data.append({
            "round_num": round_num,
            "map": map_name,
            "equipment_value_ct": eq_ct,
            "equipment_value_t": eq_t,
            "cash_ct": cash_ct,
            "cash_t": cash_t,
            "cash_spent_ct": spent_ct,
            "cash_spent_t": spent_t,
            "first_kill_side": first_kill,
            "round_winner": round_winner,
        })

    return rounds_data


def scrape_tab_scoreboard(driver: webdriver.Chrome, match_index: int) -> List[dict]:
    """We land on Scoreboard first when entering a match. Scrape player/team stats tables."""
    time.sleep(1)
    rows = _scrape_tables_on_page(driver)
    for r in rows:
        r["match_index"] = match_index
    return rows


def get_match_urls(driver: webdriver.Chrome, max_matches: int) -> List[str]:
    """
    On player profile #/matches page: find the match table and collect 'View Match' links.
    Each row has Date, Map, Score, etc. and a 'View Match' link that opens the match page.
    """
    urls: List[str] = []
    try:
        view_links = driver.find_elements(By.LINK_TEXT, "View Match")
        if not view_links:
            view_links = driver.find_elements(By.XPATH, "//a[contains(., 'View Match') or contains(., 'View match')]")
        for a in view_links:
            href = (a.get_attribute("href") or "").strip()
            if href and "match" in href and href not in urls:
                urls.append(href)
                if len(urls) >= max_matches:
                    break
    except Exception:
        pass
    if not urls:
        for a in driver.find_elements(By.TAG_NAME, "a"):
            href = a.get_attribute("href") or ""
            if "match" in href and "/match/" in href and href not in urls:
                urls.append(href)
                if len(urls) >= max_matches:
                    break
    return urls[:max_matches]


def scrape_matches(max_matches: int = MAX_MATCHES) -> dict:
    """
    Start on player profile #/matches (match list table). For each match, click 'View Match'
    to enter; we land on Scoreboard tab. Scrape Scoreboard, then Rounds (expand each round card).
    Returns dict: {"scoreboard": [...], "rounds": [...]}.
    """
    driver = create_driver(headless=False)
    all_scoreboard: List[dict] = []
    all_rounds: List[dict] = []
    try:
        driver.get(START_URL)
        time.sleep(5)
        match_urls = get_match_urls(driver, max_matches)
        if not match_urls:
            print("No 'View Match' links found. If login required, log in and press Enter.")
            input()
            time.sleep(3)
            match_urls = get_match_urls(driver, max_matches)
        if not match_urls:
            print("No match URLs found. Check that MATCHES tab is open and table is visible.")
            return {"scoreboard": [], "rounds": []}

        for match_idx, url in enumerate(match_urls):
            try:
                driver.get(url)
                time.sleep(2.5)
                mid = match_idx + 1
                map_name = get_map_from_match_page(driver)

                if "Scoreboard" in MATCH_TABS_TO_SCRAPE:
                    try:
                        rows = scrape_tab_scoreboard(driver, mid)
                        all_scoreboard.extend(rows)
                        print(f"  Match {mid} Scoreboard: {len(rows)} rows")
                    except Exception as e:
                        print(f"  Match {mid} Scoreboard error: {e}")

                if "Rounds" in MATCH_TABS_TO_SCRAPE:
                    try:
                        rounds_data = scrape_rounds_from_page(driver, map_name=map_name)
                        for r in rounds_data:
                            r["match_index"] = mid
                        all_rounds.extend(rounds_data)
                        print(f"  Match {mid} Rounds: {len(rounds_data)} rounds (map: {map_name})")
                    except Exception as e:
                        print(f"  Match {mid} Rounds error: {e}")

                print(f"Match {mid} done.")
            except Exception as e:
                print(f"Match {match_idx + 1} error: {e}")
            if match_idx < len(match_urls) - 1:
                time.sleep(SLEEP_BETWEEN_MATCHES)
    finally:
        driver.quit()

    return {"scoreboard": all_scoreboard, "rounds": all_rounds}


def _save_table_csv(rows: List[dict], path: str, key_field: str = "match_index") -> None:
    """Write list of dicts to CSV; fieldnames = key_field first, then sorted rest (for variable table columns)."""
    if not rows:
        return
    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())
    fieldnames = [key_field] if key_field in all_keys else []
    fieldnames += sorted(all_keys - {key_field})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {len(rows)} rows to {path}")


def save_to_csv(rounds: List[dict], path: str = OUTPUT_CSV) -> None:
    """Write round data to CSV (match_index, map, round_num, equipment, cash, first_kill, round_winner)."""
    if not rounds:
        return
    fieldnames = [
        "match_index", "map", "round_num", "equipment_value_ct", "equipment_value_t",
        "cash_ct", "cash_t", "cash_spent_ct", "cash_spent_t",
        "first_kill_side", "round_winner",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rounds)
    print(f"Saved {len(rounds)} rounds to {path}")


def save_all_tabs(data: dict, output_dir: str = OUTPUT_DIR) -> None:
    """Save Scoreboard and Rounds to CSVs."""
    import os
    base = output_dir.rstrip("/")
    if data.get("scoreboard"):
        _save_table_csv(data["scoreboard"], os.path.join(base, "cs2_scoreboard.csv"))
    if data.get("rounds"):
        save_to_csv(data["rounds"], path=os.path.join(base, FINAL_OUTPUT_CSV))


if __name__ == "__main__":
    print("Scraping up to", MAX_MATCHES, "matches from", START_URL)
    print("Tabs:", MATCH_TABS_TO_SCRAPE, "(Scoreboard first, then Rounds with expand per round)")
    data = scrape_matches(max_matches=MAX_MATCHES)
    save_all_tabs(data)
