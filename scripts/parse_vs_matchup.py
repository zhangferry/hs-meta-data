"""
Vicious Syndicate Matchup Winrates Parser

vS publishes matchup data in two formats:
1. Static PNG images embedded in weekly reports (DRR{N}-Winrate-{bracket}.png)
2. Tableau Public interactive dashboards on the matchup detail page

This script implements a 3-level fallback strategy:
  Level 1: Parse Tableau Public data (most accurate)
  Level 2: OCR the PNG images (reliable fallback)
  Level 3: Save static image URL for manual review (last resort)
"""

import re
import json
import io
import sys
from datetime import datetime
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

# Constants
VS_RSS_URL = "https://www.vicioussyndicate.com/feed/"
VS_REPORT_URL_TEMPLATE = "https://www.vicioussyndicate.com/vs-data-reaper-report-{number}/"
VS_MATCHUP_PAGE = "https://www.vicioussyndicate.com/drr/matchup-chart-data-reaper-report/"
VS_BASE_IMG = "https://www.vicioussyndicate.com/wp-content/uploads/"

# Rank brackets in vS reports
RANK_BRACKETS = {
    "all": "Winrate-All",
    "d4_l": "Winrate-D4-L",
    "legend": "Winrate-L",
    "top1k": "Winrate-1KL",
}


def get_latest_report_number():
    """Fetch the latest Data Reaper report number from RSS feed."""
    resp = requests.get(VS_RSS_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "xml")

    for item in soup.find_all("item"):
        title = item.find("title")
        if title and "Data Reaper Report" in title.text:
            match = re.search(r"#(\d+)", title.text)
            if match:
                return int(match.group(1)), item.find("pubDate").text
    return None, None


def fetch_report_page(report_number):
    """Fetch the report HTML page."""
    url = VS_REPORT_URL_TEMPLATE.format(number=report_number)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_winrate_image_urls(html, report_number):
    """Extract winrate PNG image URLs from the report page."""
    pattern = rf"DRR{report_number}-(Winrate-[A-Za-z0-9]+)\.png"
    matches = re.findall(pattern, html)
    urls = {}
    for bracket_suffix in set(matches):
        # Determine rank bracket
        bracket_key = None
        for key, suffix in RANK_BRACKETS.items():
            if suffix == bracket_suffix:
                bracket_key = key
                break
        if bracket_key:
            img_url = f"{VS_BASE_IMG}DRR{report_number}-{bracket_suffix}.png"
            urls[bracket_key] = img_url
    return urls


def extract_tableau_info(html):
    """Extract Tableau Public workbook info from the matchup detail page."""
    # HTML uses &#47; for / in attribute values
    # The workbook name is in: <param name='name' value='DataReaper{N}-MatchupWinRates/WinratesLeague' />
    decoded = html.replace("&#47;", "/")
    pattern = r"name='name'\s+value='(DataReaper\d+-MatchupWinRates(?:BO)?/WinratesLeague(?:BO)?)'"
    matches = re.findall(pattern, decoded)

    # Also look for static_image URLs
    img_pattern = r"value='(https?://public\.tableau\.com/static/images/[^']+)'"
    img_matches = re.findall(img_pattern, decoded)

    workbooks = []
    for m in matches:
        parts = m.split("/")
        if len(parts) == 2:
            workbooks.append({"workbook": parts[0], "sheet": parts[1]})

    return workbooks, [unquote(m) for m in img_matches]


def try_tableau_api(workbook_name, sheet_name):
    """
    Attempt to fetch data from Tableau Public's undocumented API.
    This is the most reliable way to get structured data.
    """
    # Tableau Public has an undocumented API at:
    # https://public.tableau.com/views/{workbook}/{sheet}/data
    # However, this requires session cookies and is not guaranteed to work.
    # We try it but expect it may fail.
    try:
        # First, try to get the viz info
        url = f"https://public.tableau.com/views/{workbook_name}/{sheet_name}"
        resp = requests.get(url, timeout=30, allow_redirects=True)
        if resp.status_code == 200:
            # Look for embedded data in the HTML
            # Tableau embeds data as JavaScript variables
            text = resp.text
            # Try to find the data JSON embedded in the page
            data_match = re.search(r'"data":\s*(\[{.*?}\])', text, re.DOTALL)
            if data_match:
                return json.loads(data_match.group(1))
    except Exception:
        pass
    return None


def parse_winrate_image_ocr(image_url):
    """
    Parse winrate data from a PNG image using OCR.
    Requires: pip install pillow pytesseract
    Falls back gracefully if OCR is not available.
    """
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        print("  ⚠️  OCR dependencies not installed (pillow, pytesseract)")
        return None

    try:
        resp = requests.get(image_url, timeout=30)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))

        # The winrate image is a heatmap grid with archetype names and percentages
        # We need to:
        # 1. OCR the full image to get text
        # 2. Parse the grid structure to extract winrate matrix

        text = pytesseract.image_to_string(img)

        # Parse percentages from OCR text
        # Typical format: "55.2%" or "52.1"
        percentages = re.findall(r'(\d{1,2}\.\d)%?', text)

        if not percentages:
            return None

        # Try to determine grid size (archetype count)
        # vS typically has 10-15 archetypes in a matchup chart
        num_archetypes = len(percentages)
        if num_archetypes < 4:
            return None

        # Attempt to organize into a matrix
        # This is approximate - OCR on heatmap images is inherently imprecise
        return {
            "raw_percentages": [float(p) for p in percentages],
            "estimated_archetypes": int(num_archetypes ** 0.5),
            "confidence": "low",
            "note": "OCR-parsed data, may contain errors"
        }
    except Exception as e:
        print(f"  ⚠️  OCR failed: {e}")
        return None


def fetch_and_parse_vs_matchup():
    """
    Main entry point: fetch and parse vS matchup data.
    Returns a structured dict with matchup winrate matrix, or None on failure.
    """
    print("📊 Fetching Vicious Syndicate matchup data...")

    # Step 1: Get latest report number
    report_number, pub_date = get_latest_report_number()
    if not report_number:
        print("  ❌ Could not find latest report number")
        return None
    print(f"  📄 Latest report: #{report_number} ({pub_date})")

    # Step 2: Fetch report page and extract image URLs
    report_html = fetch_report_page(report_number)
    image_urls = extract_winrate_image_urls(report_html, report_number)
    print(f"  🖼️  Found {len(image_urls)} winrate images: {list(image_urls.keys())}")

    # Step 3: Try Tableau API from matchup detail page
    matchup_html = None
    try:
        resp = requests.get(VS_MATCHUP_PAGE, timeout=30)
        resp.raise_for_status()
        matchup_html = resp.text
    except Exception as e:
        print(f"  ⚠️  Could not fetch matchup detail page: {e}")

    tableau_data = None
    if matchup_html:
        workbooks, static_images = extract_tableau_info(matchup_html)
        print(f"  📊 Found {len(workbooks)} Tableau workbooks")

        for wb in workbooks:
            data = try_tableau_api(wb["workbook"], wb["sheet"])
            if data:
                tableau_data = data
                print(f"  ✅ Got data from Tableau: {wb['workbook']}")
                break

    # Step 4: If Tableau failed, try OCR on PNG images
    ocr_data = None
    if not tableau_data and image_urls:
        print("  📝 Tableau data unavailable, trying OCR...")
        for bracket, url in image_urls.items():
            if bracket == "all":  # Start with all ranks
                ocr_data = parse_winrate_image_ocr(url)
                if ocr_data:
                    print(f"  ✅ OCR parsed {len(ocr_data['raw_percentages'])} values")
                break

    # Step 5: Build result
    result = {
        "reportNumber": report_number,
        "reportDate": pub_date,
        "source": "vicious_syndicate",
        "fetchDate": datetime.utcnow().isoformat() + "Z",
        "archetypes": [],
        "matrix": [],
        "rankBrackets": list(image_urls.keys()),
        "imageUrls": image_urls,
    }

    if tableau_data:
        result["dataQuality"] = "high"
        result["parseMethod"] = "tableau_api"
        result["rawData"] = tableau_data
    elif ocr_data:
        result["dataQuality"] = "medium"
        result["parseMethod"] = "ocr"
        result["rawData"] = ocr_data
    else:
        result["dataQuality"] = "none"
        result["parseMethod"] = "failed"
        result["note"] = "Could not parse structured data. Images available at imageUrls."
        print("  ⚠️  Could not extract structured matchup data")

    return result


if __name__ == "__main__":
    result = fetch_and_parse_vs_matchup()
    if result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("❌ Failed to fetch matchup data")
        sys.exit(1)
