# paylocity_strategy.py
# This module contains the parsing strategy for Paylocity job boards.

import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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
            # Example of removing boilerplate text.
            for p in description_element.find_all('p', string=lambda t: t and "At B&A, we foster" in t):
                p.decompose()
            strong_tag = description_element.find('strong', string=lambda t: t and "More About B&A" in t)
            if strong_tag and strong_tag.find_parent('p'):
                for sibling in strong_tag.find_parent('p').find_next_siblings():
                    sibling.decompose()
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