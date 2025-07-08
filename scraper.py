# scraper.py
# This module handles all web scraping, HTML parsing, and AI interaction.
# Now with multiple parsing strategies.

import os
import time
import json
import re
import httpx 
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException


# --- Request Counters ---
GEMINI_REQUEST_COUNT = 0 
SELENIUM_PAGE_LOADS = 0


# --- Main Scraping and AI Functions ---

def check_job_for_keywords(text_to_check, keywords):
    """Checks if a string of text contains any of the specified keywords."""
    if not text_to_check: return None, []
    text_lower = text_to_check.lower()
    matched = [kw for kw in keywords if kw.lower() in text_lower]
    return text_lower if bool(matched) else None, matched

def format_job_card(details, link, company_name, matched_keywords):
    """Formats the scraped data into a structured dictionary (job_card)."""
    unique_job_id = "N/A"
    
    # --- More robust method to get the Unique Job ID ---
    try:
        parsed_url = urlparse(link)
        query_params = parse_qs(parsed_url.query)
        
        common_id_params = ['jobId', 'gh_jid', 'reqid', 'id', 'jobID', 'p_jid']
        for param in common_id_params:
            if param in query_params:
                unique_job_id = query_params[param][0]
                break
        
        if unique_job_id == "N/A":
            path_match = re.search(r'/(\d{4,})/?$', parsed_url.path)
            if path_match:
                unique_job_id = path_match.group(1)

        if unique_job_id == "N/A":
            job_id_match = re.search(r'[=/]([a-zA-Z0-9_-]{6,})/?$', link)
            if job_id_match:
                unique_job_id = job_id_match.group(1)

    except Exception as e:
        print(f"  -> Could not parse Job ID from link {link}. Error: {e}")

    if unique_job_id != "N/A":
        unique_job_id = f"{company_name.upper().replace(' ', '')}-{unique_job_id}"

    if not isinstance(details, dict):
        return {"Company": company_name, "Job Title": "Details Extraction Failed", "Location": "N/A", "Matched Keywords": matched_keywords, "Link to Job": link, "Unique Job ID": unique_job_id}
    
    return {"Company": company_name, "Job Title": details.get("job_title", "Title Not Found"), "Location": details.get("location", "Location Not Found"), "Matched Keywords": matched_keywords, "Link to Job": link, "Unique Job ID": unique_job_id}

def save_raw_data_to_json(data, filename="raw_scraper_output.json"):
    """Saves the raw, unprocessed scraped data to a JSON file for debugging."""
    print(f"\n  -> Saving {len(data)} raw scraped items to {filename}...")
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        print(f"  -> ✅ Successfully saved results to {filename}")
    except Exception as e:
        print(f"  -> ❌ Failed to save raw data to {filename}: {e}")

# --- Generic Validation Function (Step 3) ---
def validate_and_format_jobs(all_job_details, company):
    """Takes a list of scraped job data and checks each one for keywords."""
    found_jobs = []
    print(f"\n  -> All details fetched. Now scanning {len(all_job_details)} jobs for keywords...")
    for i, job_data in enumerate(all_job_details):
        full_text_to_check = f"{job_data['title']} {job_data['location']} {job_data['description']}"
        validated_text, matched_keywords = check_job_for_keywords(full_text_to_check, company['keywords'])

        if validated_text:
            print(f"    ({i+1}/{len(all_job_details)}) ✅ MATCH FOUND! Keywords: {', '.join(matched_keywords)} in '{job_data['title']}'")
            details = {"job_title": job_data['title'], "location": job_data['location']}
            job_card = format_job_card(details, job_data['link'], company['company_name'], matched_keywords)
            found_jobs.append(job_card)
    return found_jobs

# --- NEW: Parser Strategy Greenhouse API (Efficient & More Robust) ---
async def parse_strategy_greenhouse_api(soup, company):
    """
    Fetches all job details from a Greenhouse board using its JSON API.
    This is much faster and more reliable than using Selenium.
    """
    print("  -> Using Greenhouse API parsing strategy.")
    
    board_token = None
    
    # Method 1: Try to find the board token from the standard script tag.
    script_tag = soup.find('script', src=re.compile(r'boards.greenhouse.io/embed/job_board'))
    if script_tag:
        match = re.search(r'job_board\?for=([^&]+)', script_tag['src'])
        if match:
            board_token = match.group(1)
            print("    -> Found board token via script tag.")

    # Method 2: If the script isn't found, guess the token from the company name.
    if not board_token:
        print("    -> Script tag not found. Guessing board token from company name.")
        # Sanitize the company name to create a likely token.
        # Example: "Dev Technology " -> "devtechnology"
        board_token = re.sub(r'[^a-z0-9]', '', company['company_name'].lower().strip())
        if not board_token:
            print("  -> ❌ Could not create a valid board token from the company name.")
            return []

    print(f"    -> Using board token: {board_token}")
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    
    async with httpx.AsyncClient() as client:
        try:
            print(f"    -> Querying API: {api_url}")
            response = await client.get(api_url, timeout=30)
            response.raise_for_status()
            api_data = response.json()
            
            all_job_details = []
            for job in api_data.get('jobs', []):
                # The API provides a full job description, but we need to fetch it
                # if the `content` field is not included in this basic response.
                job_content = job.get('content')
                if not job_content and job.get('id'):
                    # Fetch detailed content if not present
                    detail_api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job.get('id')}"
                    detail_response = await client.get(detail_api_url)
                    if detail_response.status_code == 200:
                        job_content = detail_response.json().get('content', '')
                
                description_soup = BeautifulSoup(job_content or '', 'html.parser')
                
                all_job_details.append({
                    "title": job.get('title', 'Title Not Found').strip(),
                    "location": job.get('location', {}).get('name', 'Location Not Found').strip(),
                    "link": job.get('absolute_url', '#').strip(),
                    "description": description_soup.get_text(" ", strip=True)
                })
            print(f"    -> Successfully fetched {len(all_job_details)} jobs from the API.")
            return all_job_details
        except httpx.HTTPStatusError as e:
            print(f"  -> ❌ Failed to fetch data from Greenhouse API. Status: {e.response.status_code}. URL: {api_url}")
            return []
        except httpx.RequestError as e:
            print(f"  -> ❌ Network error while fetching from Greenhouse API: {e}")
            return []
        except json.JSONDecodeError:
            print("  -> ❌ Failed to parse JSON response from Greenhouse API.")
            return []


# --- Parser Strategy Paylocity ---
async def fetch_paylocity_details_async(client, link):
    """Asynchronously fetches and parses a single Paylocity job page."""
    try:
        response = await client.get(link, timeout=15)
        response.raise_for_status()
        details_soup = BeautifulSoup(response.text, 'html.parser')
        
        title = (details_soup.select_one('span.job-preview-title span') or details_soup.select_one('h1')).get_text(strip=True)
        location = (details_soup.select_one('div.preview-location')).get_text(strip=True)
        description_element = details_soup.select_one('div.job-preview-details > div:nth-of-type(3)')
        if description_element:
            for p in description_element.find_all('p', string=lambda t: t and "At B&A, we foster" in t): p.decompose()
            strong_tag = description_element.find('strong', string=lambda t: t and "More About B&A" in t)
            if strong_tag and strong_tag.find_parent('p'):
                for sibling in strong_tag.find_parent('p').find_next_siblings(): sibling.decompose()
                strong_tag.find_parent('p').decompose()
            description = description_element.get_text(strip=True)
        else:
            description = ""
        return {"link": link, "title": title, "location": location, "description": description}
    except Exception as e:
        print(f"  -> Failed to fetch {link}: {e}")
        return None

async def parse_strategy_paylocity(soup, company):
    """Gathers all job links from a Paylocity page and fetches their details concurrently."""
    print("  -> Using Paylocity parsing strategy.")
    job_links = [urljoin(company['careers_url'], a['href']) for a in soup.select('div.job-listing-job-item a[href*="/Jobs/Details/"]')]
    print(f"    -> Found {len(job_links)} potential job links on the main page.")
    
    async with httpx.AsyncClient() as client:
        tasks = [fetch_paylocity_details_async(client, link) for link in job_links]
        print(f"\n  -> Fetching details for {len(tasks)} job pages concurrently...")
        results = await asyncio.gather(*tasks)
        return [res for res in results if res]

# --- FINAL ADP STRATEGY: Click, Scrape, and Reload ---
async def parse_strategy_adp_clickthrough(driver, company):
    """
    Uses the stable "Click and Reload" method and scrapes full job details
    from the detail page during each loop.
    """
    print("  -> Using ADP 'Click, Scrape, and Reload' strategy.")
    all_job_details = []
    initial_url = driver.current_url

    try:
        view_all_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "View all")] | //sdf-button[contains(text(), "View all")]'))
        )
        print("    -> 'View all' button found. Clicking...")
        driver.execute_script("arguments[0].click();", view_all_button)
        time.sleep(3)
    except TimeoutException:
        print("    -> 'View all' button not found, proceeding.")

    job_item_selector = (By.CLASS_NAME, "current-openings-item")
    list_container_selector = (By.CLASS_NAME, "current-openings-list")
    WebDriverWait(driver, 10).until(EC.presence_of_element_located(list_container_selector))
    num_jobs = len(driver.find_elements(*job_item_selector))
    print(f"    -> Found {num_jobs} job items to process.")

    for i in range(num_jobs):
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located(list_container_selector))
            job_items = driver.find_elements(*job_item_selector)
            if i >= len(job_items):
                print(f"    -> List seems to have shrunk. Stopping at item {i}.")
                break

            item = job_items[i]
            title_text_from_list = item.find_element(By.TAG_NAME, "sdf-link").text.strip()
            print(f"      -> Processing ({i+1}/{num_jobs}): {title_text_from_list}")

            driver.execute_script("arguments[0].click();", item)
            WebDriverWait(driver, 15).until(EC.url_contains("jobId="))
            job_link = driver.current_url

            print("      -> Scraping full details...")
            details_soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            title = details_soup.select_one('h2.job-description-title').get_text(strip=True)
            location = ", ".join([loc.get_text(strip=True) for loc in details_soup.select('.job-description-location-item span')])

            description_element = details_soup.select_one('div.job-description-data-item')
            description = "Description not found."
            if description_element:
                description_parts = []
                for tag in description_element.find_all(['p', 'ul', 'ol']):
                    if "Information Technology Strategies, Inc." in tag.get_text():
                        continue
                    if "Work With Us" in tag.get_text():
                        break
                    description_parts.append(tag.get_text(" ", strip=True))
                if description_parts:
                    description = "\n".join(description_parts)

            all_job_details.append({
                "title": title,
                "location": location if location else "Location not specified",
                "link": job_link,
                "description": description 
            })

            print("      -> Reloading main job list...")
            driver.get(initial_url)
            
            try:
                view_all_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "View all")] | //sdf-button[contains(text(), "View all")]'))
                )
                driver.execute_script("arguments[0].click();", view_all_button)
                time.sleep(3)
            except TimeoutException:
                pass 

        except Exception as e:
            print(f"    -> ERROR processing item {i+1}. Skipping. Reason: {e}")
            continue
            
    return all_job_details


# --- Main Processing Controller ---
async def process_company(driver, company):
    """Controller function that selects the correct parsing strategy based on the URL or page content."""
    global SELENIUM_PAGE_LOADS
    print(f"\n{'='*20}\nProcessing: {company['company_name']}")
    print(f"Keywords: {', '.join(company['keywords'])}\n{'='*20}")
    
    # Load the initial page for all strategies.
    print(f"  -> Navigating to: {company['careers_url']}")
    driver.get(company['careers_url'])
    SELENIUM_PAGE_LOADS += 1
    
    all_job_details = []
    
    # --- REFINED STRATEGY SELECTION ---
    
    # Strategy 1: Check for Paylocity by URL
    if 'recruiting.paylocity.com' in driver.current_url:
        print("  -> Paylocity site detected. Using concurrent fetch strategy.")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        all_job_details = await parse_strategy_paylocity(soup, company)
    
    # Strategy 2: Check for ADP by URL
    elif 'workforcenow.adp.com' in driver.current_url:
        print("  -> ADP site detected. Using click-through strategy.")
        all_job_details = await parse_strategy_adp_clickthrough(driver, company)
        
    # Default Strategy: Check for a Greenhouse integration
    else:
        try:
            # Wait for an element that indicates a Greenhouse board is present.
            # This is more flexible and covers both standard and custom integrations.
            # It checks for the standard div ID OR the specific link class you found.
            print("  -> Checking for Greenhouse job board...")
            greenhouse_indicator_xpath = "//*[@id='grnhse_app'] | //a[contains(@class, 'board-list__item')]"
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, greenhouse_indicator_xpath))
            )
            print("  -> Greenhouse job board detected. Using API strategy.")
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            all_job_details = await parse_strategy_greenhouse_api(soup, company)
        except TimeoutException:
            # If no indicator is found, we assume no strategy applies.
            print("  -> ⚠️ No specific parsing strategy found for this site. No jobs will be processed.")
            all_job_details = []

    if all_job_details:
        save_raw_data_to_json(all_job_details)

    return validate_and_format_jobs(all_job_details, company)
