import re
import time
import json
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


OUT_DIR = Path("rti_print_all_details_pdfs").resolve()
OUT_DIR.mkdir(exist_ok=True)


def setup_driver():
    app_state = {
        "recentDestinations": [
            {"id": "Save as PDF", "origin": "local", "account": ""}
        ],
        "selectedDestinationId": "Save as PDF",
        "version": 2,
        "isHeaderFooterEnabled": False,
        "isCssBackgroundEnabled": True,
    }

    prefs = {
        "printing.print_preview_sticky_settings.appState": json.dumps(app_state),
        "savefile.default_directory": str(OUT_DIR),
        "download.default_directory": str(OUT_DIR),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    }

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--kiosk-printing")
    options.add_experimental_option("prefs", prefs)

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )


def wait_body(driver, timeout=25):
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )


def get_rti_ids(driver):
    text = driver.find_element(By.TAG_NAME, "body").text
    return list(dict.fromkeys(re.findall(r"\b22\d{13}\b", text)))


def scroll_right(driver):
    driver.execute_script("""
        document.querySelectorAll('*').forEach(e => {
            if (e.scrollWidth > e.clientWidth) {
                e.scrollLeft = e.scrollWidth;
            }
        });
    """)


def scroll_left(driver):
    driver.execute_script("""
        document.querySelectorAll('*').forEach(e => {
            if (e.scrollWidth > e.clientWidth) {
                e.scrollLeft = 0;
            }
        });
    """)


def click_view(driver, rti_id):
    row = WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((By.XPATH, f"//tr[contains(., '{rti_id}')]"))
    )

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
    time.sleep(1)

    scroll_right(driver)
    time.sleep(1)

    view_btn = WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((
            By.XPATH,
            f"//tr[contains(., '{rti_id}')]//*[self::button or self::a][contains(., 'View')]"
        ))
    )

    driver.execute_script("arguments[0].click();", view_btn)
    time.sleep(5)


def wait_for_new_pdf(before_files, rti_id, timeout=90):
    start = time.time()

    while time.time() - start < timeout:
        downloading = list(OUT_DIR.glob("*.crdownload"))
        if downloading:
            time.sleep(1)
            continue

        current = set(OUT_DIR.glob("*.pdf"))
        new_files = list(current - before_files)

        if new_files:
            newest = max(new_files, key=lambda p: p.stat().st_mtime)
            target = OUT_DIR / f"{rti_id}.pdf"

            if target.exists():
                target.unlink()

            newest.rename(target)
            print(f"[OK] Saved: {target.name}")
            return True

        time.sleep(1)

    print(f"[WARN] PDF not detected: {rti_id}")
    return False


def click_print_all_details(driver, rti_id):
    before_files = set(OUT_DIR.glob("*.pdf"))

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    btn = WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((
            By.XPATH,
            "//*[self::button or self::a][contains(., 'Print All Details')]"
        ))
    )

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    time.sleep(1)

    driver.execute_script("arguments[0].click();", btn)
    print(f"[INFO] Print All Details clicked: {rti_id}")

    wait_for_new_pdf(before_files, rti_id)


def process_page(driver):
    wait_body(driver)
    time.sleep(2)

    rti_ids = get_rti_ids(driver)
    print(f"Found {len(rti_ids)} RTIs on this page")

    for rti_id in rti_ids:
        target = OUT_DIR / f"{rti_id}.pdf"

        if target.exists():
            print(f"[SKIP] {rti_id}.pdf")
            continue

        print(f"Opening View for RTI: {rti_id}")

        try:
            click_view(driver, rti_id)
            click_print_all_details(driver, rti_id)

            driver.back()
            wait_body(driver)
            time.sleep(4)

        except Exception as e:
            print(f"[ERROR] Failed {rti_id}: {e}")
            try:
                driver.back()
                wait_body(driver)
                time.sleep(4)
            except Exception:
                pass


def click_next(driver):
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1)

    scroll_left(driver)
    time.sleep(1)

    old_ids = set(get_rti_ids(driver))

    buttons = driver.find_elements(
        By.XPATH,
        "//*[self::a or self::button]"
        "[normalize-space()='>' or normalize-space()='>>' or contains(., 'Next')]"
    )

    for btn in buttons:
        try:
            if btn.is_displayed() and btn.is_enabled():
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(5)

                new_ids = set(get_rti_ids(driver))
                if new_ids and new_ids != old_ids:
                    return True
        except Exception:
            continue

    return False


def main():
    driver = setup_driver()

    driver.get("https://rtionline.cg.gov.in/rtiApplicationList/3/1")

    input("Login in Chrome, open RTI list page, then press ENTER here...")

    page = 1

    while True:
        print(f"\n========== PAGE {page} ==========")
        process_page(driver)

        if not click_next(driver):
            print("No next page found.")
            break

        page += 1

    print("\nDONE")
    print(f"Saved folder: {OUT_DIR}")

    driver.quit()


if __name__ == "__main__":
    main()