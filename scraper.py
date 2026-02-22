"""
Automated CS2 Match Scraper (csstats.gg).
Iterates through up to 22 matches, extracts round-level data and scoreboard, saves to CSV.

Note: The site may require login to view player stats. Run Chrome with Selenium;
you can log in manually when the browser opens, then the script continues.
"""

import csv
import os
import re
import time
from typing import List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# Scraper config: player matches URL, how many matches to scrape, output paths.
START_URL = "https://csstats.gg/player/76561198812851717#/matches"
MAX_MATCHES = 22
SLEEP_BETWEEN_MATCHES = 3
FINAL_OUTPUT_CSV = "cs2_final_clean_data.csv"
MATCH_TABS_TO_SCRAPE = ["Scoreboard", "Rounds"]
OUTPUT_DIR = "."

# Text labels used to find economic rows and round outcome in the round card HTML.
EQUIPMENT_VALUE_LABEL = "Equipment Value"
CASH_LABEL = "Cash"
CASH_SPENT_LABEL = "Cash Spent"
TERRORISTS_WIN_TEXT = "Terrorists Win"
COUNTER_TERRORISTS_WIN_TEXT = "Counter-Terrorists Win"


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


def _click_rounds_tab(driver: webdriver.Chrome) -> bool:
    """Switch match page to the Rounds tab (JS content_tab or click on rounds-nav)."""
    try:
        driver.execute_script("if (typeof content_tab === 'function') { content_tab('rounds'); }")
        time.sleep(1.2)
        driver.find_element(By.CSS_SELECTOR, "#match-rounds, [id^='round-info-']")
        return True
    except Exception:
        pass
    try:
        wait = WebDriverWait(driver, 10)
        tab = wait.until(EC.presence_of_element_located((By.ID, "rounds-nav")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", tab)
        time.sleep(1.2)
        return True
    except (TimeoutException, NoSuchElementException):
        return False


def _wait_for_round_cards(driver: webdriver.Chrome, timeout: int = 15) -> None:
    """Wait until the Rounds tab content (e.g. round-info-1 or 'Round 1') is present."""
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.presence_of_element_located((By.XPATH, "//*[@id='round-info-1' or contains(@class,'round-info') or contains(., 'Round 1')]")))


def _scrape_tables_on_page(driver: webdriver.Chrome) -> List[dict]:
    """Scrape all visible HTML tables: first row as headers, each row as a dict."""
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


def get_map_from_match_page(driver: webdriver.Chrome) -> Optional[str]:
    """Extract map name (e.g. de_mirage) from the current match page."""
    try:
        for el in driver.find_elements(By.XPATH, "//*[contains(., 'de_')]"):
            text = (el.text or "").strip()
            if text and re.match(r"de_[a-z0-9_]+", text, re.I):
                return text.split()[0] if text else None
        m = re.search(r"\b(de_[a-z0-9_]+)\b", driver.find_element(By.TAG_NAME, "body").text, re.I)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _get_economic_row(container, label: str) -> Tuple[Optional[int], Optional[int]]:
    """Find row by label (Equipment Value, Cash, Cash Spent); return (T value, CT value) as ints."""
    try:
        label_el = container.find_element(By.XPATH, f".//*[contains(normalize-space(.), '{label}')]")
    except NoSuchElementException:
        return None, None
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
    """Get equipment value row: (T, CT)."""
    return _get_economic_row(container, EQUIPMENT_VALUE_LABEL)


def _get_first_kill_side_from_kill_feed(round_card) -> Optional[str]:
    """From kill feed first entry, return killer side: 'CT' or 'T' (by span.team-ct / team-t)."""
    try:
        first_entry = round_card.find_element(By.CSS_SELECTOR, ".tl-inner")
    except NoSuchElementException:
        entries = round_card.find_elements(By.CSS_SELECTOR, "[class*='tl-inner'], [class*='kill']")
        first_entry = entries[0] if entries else None
    if not first_entry:
        return None
    try:
        team_spans = first_entry.find_elements(By.CSS_SELECTOR, "span.team-ct, span.team-t")
        if not team_spans:
            return None
        cls = (team_spans[0].get_attribute("class") or "").lower()
        if "team-ct" in cls:
            return "CT"
        if "team-t" in cls:
            return "T"
    except NoSuchElementException:
        pass
    return None


def _get_round_winner_from_card(round_card) -> Optional[str]:
    """Return round winner from card text: 'CT' or 'T' if found, else None."""
    text = round_card.text
    if COUNTER_TERRORISTS_WIN_TEXT.lower() in text.lower() or "counter-terrorists win" in text.lower():
        return "CT"
    if TERRORISTS_WIN_TEXT.lower() in text.lower() or "terrorists win" in text.lower():
        return "T"
    return None


def scrape_rounds_from_page(driver: webdriver.Chrome, map_name: Optional[str] = None) -> List[dict]:
    """Open Rounds tab, expand each round card, scrape economy + first kill + winner per round."""
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

    def _scrape_one_card(container):
        """Parse one expanded round card into economy values, first_kill_side, round_winner."""
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
    """Scrape Scoreboard tab tables and add match_index to each row."""
    time.sleep(1)
    rows = _scrape_tables_on_page(driver)
    for r in rows:
        r["match_index"] = match_index
    return rows


def get_match_urls(driver: webdriver.Chrome, max_matches: int) -> List[str]:
    """Collect 'View Match' links from the matches list page, up to max_matches."""
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
    """Open START_URL, collect match URLs, then for each match scrape Scoreboard + Rounds. Returns {scoreboard, rounds}."""
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
    """Write list of dicts to CSV; columns = key_field first, then rest sorted."""
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


def save_to_csv(rounds: List[dict], path: str = FINAL_OUTPUT_CSV) -> None:
    """Write round data to CSV with fixed columns (match_index, map, round_num, economy, first_kill, round_winner)."""
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
    """Save scoreboard and rounds from data dict to cs2_scoreboard.csv and cs2_final_clean_data.csv."""
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
