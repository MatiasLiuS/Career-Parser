# adp_strategy.py
import asyncio
import re  # Import the regular expression module
from bs4 import BeautifulSoup

async def parse_adp_job_pages(driver, job_links: list) -> list:
    """
    Visits each job link from a list, parses the HTML for job details,
    and returns a list of structured job data.
    """
    all_job_details = []
    total_links = len(job_links)
    print(f"\n  -> Scraping details from {total_links} individual job links...")

    for i, link in enumerate(job_links):
        print(f"    ({i+1}/{total_links}) Scraping: {link}")
        try:
            driver.get(link)
            # A small, explicit wait can help ensure the page elements are rendered
            await asyncio.sleep(1) 
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- Extract data using the selectors you provided ---
            try:
                title = soup.select_one("h2.job-description-title").text.strip()
            except AttributeError:
                title = "Title not found"

            try:
                location = soup.select_one(".job-description-location-item span").text.strip()
            except AttributeError:
                location = "Location not found"

            try:
                # Get the raw description
                description_raw = soup.select_one(".job-description-data").get_text(separator="\n", strip=True)
            except AttributeError:
                description_raw = "Description not found"
            
            # --- NEW: Description Cleaning Logic ---
            cleaned_description = description_raw

            # 1. Cut off everything at and below "Work With Us"
            if "Work With Us" in cleaned_description:
                cleaned_description = cleaned_description.split("Work With Us")[0].strip()

            # 2. Remove the first paragraph (the boilerplate)
            # This regex finds the specific intro paragraph and removes it.
            boilerplate_pattern = r"Information Technology Strategies, Inc\. is a government IT solutions provider.*?to work for our company\."
            cleaned_description = re.sub(boilerplate_pattern, '', cleaned_description, flags=re.IGNORECASE | re.DOTALL).strip()


            # --- Compile the scraped data ---
            all_job_details.append({
                'title': title,
                'location': location,
                'description': cleaned_description, # Use the final cleaned version
                'link': link
            })

        except Exception as e:
            print(f"    ❌ Failed to process link {link}. Error: {e}")
            continue
            
    return all_job_details