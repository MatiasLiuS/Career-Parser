from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time, zlib, json

def get_adp_job_links(company_url: str, cid: str, ccid: str):
    """Launches headless browser, clicks through ADP UI, and returns list of job links."""
    
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")

    driver = webdriver.Chrome(options=options)

    print("🌐 Opening ADP page...")
    driver.get(company_url)

    try:
        print("🖱️ Clicking 'View all' button via JS...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "recruitment_careerCenter_showAllJobs"))
        )
        driver.execute_script("""
            const btn = document.querySelector("#recruitment_careerCenter_showAllJobs");
            if (btn) btn.click();
        """)
        time.sleep(5)
    except Exception as e:
        print(f"⚠️ Could not click 'View all': {e}")

    print("🔍 Scanning network requests...")
    all_string_values = []

    for request in driver.requests:
        if request.response:
            url = request.url
            ct = request.response.headers.get("Content-Type", "")
            if "job-requisitions" in url and "application/json" in ct:
                try:
                    body = request.response.body
                    if request.response.headers.get('Content-Encoding') == 'gzip':
                        body = zlib.decompress(body, zlib.MAX_WBITS | 16)
                    data = json.loads(body.decode('utf-8'))

                    def extract_strings(obj):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if k == "stringValue" and v.strip():
                                    all_string_values.append(v.strip())
                                extract_strings(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                extract_strings(item)

                    extract_strings(data)

                except Exception as e:
                    print("❌ Failed to parse job data:", e)

    driver.quit( )

    base_url = "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html"
    job_links = [
        f"{base_url}?cid={cid}&ccId={ccid}&lang=en_US&selectedMenuKey=CareerCenter&jobId={job_id}"
        for job_id in all_string_values
    ]

    return job_links
