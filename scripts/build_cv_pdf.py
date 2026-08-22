import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
SOURCE_HTML = ROOT / "src" / "cv" / "cv.html"
OUTPUT_DIR = ROOT / "src" / "cv" / "output"
OUTPUT_PDF = Path.home() / "Desktop" / "Aleksander_Kunysz_Data_Engineer_CV.pdf"


def _find_browser() -> Optional[str]:
    candidates = [
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "msedge",
        "brave",
        "chrome",
    ]

    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    common_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Chromium\Application\chrome.exe",
        r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
    ]

    for path in common_paths:
        if os.path.exists(path):
            return path

    return None


def _generate_with_browser(browser: str, html_path: str, output_pdf: str) -> None:
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",  # Ukrywa nagłówki (data, URL) z przeglądarki
        f"--print-to-pdf={output_pdf}",
        html_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("Generowanie PDF zakończyło się błędem.")


def _generate_with_playwright(html_path: str, output_pdf: str) -> None:
    if importlib.util.find_spec("playwright") is None:
        raise RuntimeError("Playwright is not installed")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(Path(html_path).resolve().as_uri())
        page.pdf(
            path=output_pdf,
            format="A4",
            print_background=True,
            margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
        )
        browser.close()


def main() -> None:
    if not SOURCE_HTML.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku HTML: {SOURCE_HTML}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = SOURCE_HTML.resolve().as_posix()
    output_pdf = (OUTPUT_DIR / "cv.pdf").resolve().as_posix()
    output_html = OUTPUT_DIR / "cv.html"
    output_html.write_text(SOURCE_HTML.read_text(encoding="utf-8"), encoding="utf-8")

    browser = _find_browser()
    generated_pdf = False

    if browser:
        print(f"Generuję PDF z HTML za pomocą: {browser}")
        try:
            _generate_with_browser(browser, html_path, output_pdf)
            generated_pdf = True
        except Exception as exc:
            print(f"Nie udało się wygenerować PDF przez przeglądarkę: {exc}")

    if not generated_pdf:
        try:
            _generate_with_playwright(html_path, output_pdf)
            generated_pdf = True
        except Exception as exc:
            print(f"Playwright nie jest dostępny lub nie zadziałał: {exc}")

    if generated_pdf:
        # Kopiowanie gotowego PDF na Pulpit oraz pozostawienie pliku w src/cv/output/cv.pdf
        OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PDF.write_bytes(Path(output_pdf).read_bytes())
        print(f"PDF gotowy w katalogu projektu: {output_pdf}")
        print(f"Kopia PDF na Pulpicie: {OUTPUT_PDF}")
    else:
        print(
            "Brak dostępnego renderera PDF. Zapisuję wersję HTML do otwarcia i wydrukowania do PDF."
        )
        print(f"HTML gotowy do otwarcia: {output_html}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        sys.exit(1)
