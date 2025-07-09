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

# --- Import the modularized strategies ---
from paylocity_strategy import parse_strategy_paylocity
from greenhouse_strategy import parse_strategy_greenhouse_api
from adp_strategy import parse_adp_job_pages
from get_links import get_adp_job_links

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
    
    try:
        if 'recruiting.paylocity.com' in link:
            paylocity_match = re.search(r'/Details/(\d+)', link)
            if paylocity_match:
                unique_job_id = paylocity_match.group(1)

        if unique_job_id == "N/A":
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
        sanitized_company_name = re.sub(r'[^A-Z0-9]', '', company_name.upper())
        unique_job_id = f"{sanitized_company_name}-{unique_job_id}"

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


# --- Main Processing Controller ---
async def process_company(driver, company):
    """Controller function that selects the correct parsing strategy based on the URL or page content."""
    global SELENIUM_PAGE_LOADS
    print(f"\n{'='*20}\nProcessing: {company['company_name']}")
    print(f"Keywords: {', '.join(company['keywords'])}\n{'='*20}")
    
    print(f"  -> Navigating to: {company['careers_url']}")
    driver.get(company['careers_url'])
    SELENIUM_PAGE_LOADS += 1
    
    all_job_details = []
    
    # --- STRATEGY SELECTION ---
    
    

    if 'recruiting.paylocity.com' in driver.current_url:
        print("  -> Paylocity site detected. Using concurrent fetch strategy.")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        all_job_details = await parse_strategy_paylocity(soup, company)
    # Strategy 1: Check for Paylocity by URL
      # --- MODIFICATION: Add ADP strategy ---
    elif 'workforcenow.adp.com' in driver.current_url:
        print("  -> ADP site detected. Using API Intercept strategy.")
        cid = "750c862e-b802-49e4-952d-5049b07cf887"
        ccid = "19000101_000001"
        company_url ="https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid=750c862e-b802-49e4-952d-5049b07cf887&ccId=19000101_000001&lang=en_US&selectedMenuKey=CareerCenter"
        
        job_links = get_adp_job_links(company_url, cid, ccid)

  
        all_job_details = await parse_adp_job_pages(driver, job_links)
    # Strategy 2: Check for a Greenhouse integration on the page
    else:
        try:
            print("  -> Checking for Greenhouse job board...")
            # This XPath checks for either the main Greenhouse app container OR a common link class
            greenhouse_indicator_xpath = "//*[@id='grnhse_app'] | //a[contains(@class, 'board-list__item')]"
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, greenhouse_indicator_xpath))
            )
            print("  -> Greenhouse job board detected. Using API strategy.")
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            # Call the imported function
            all_job_details = await parse_strategy_greenhouse_api(soup, company)
        except TimeoutException:
            print("  -> ⚠️ No specific parsing strategy found for this site. No jobs will be processed.")
            all_job_details = []

    # if all_job_details:
    #     save_raw_data_to_json(all_job_details)

    return validate_and_format_jobs(all_job_details, company)