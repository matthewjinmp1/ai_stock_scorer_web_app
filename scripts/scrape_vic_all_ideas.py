import requests
from bs4 import BeautifulSoup
import re
import csv
import time
import os
from datetime import datetime

def scrape_vic_all_ideas(output_file='data/vic_all_ideas.csv'):
    """
    Scrapes all historical ideas from VIC and stores them in a CSV.
    """
    if not os.path.exists('data'):
        os.makedirs('data')
        
    # Headers for CSV
    fieldnames = ['ticker', 'company', 'position', 'date', 'url']
    
    # Check if file exists to resume or start fresh
    file_exists = os.path.isfile(output_file)
    
    # List of groups and years to iterate through
    groups = ['0-9', 'A-C', 'D-F', 'G-J', 'K-N', 'O-R', 'S-V', 'W-Z']
    current_year = datetime.now().year
    years = list(range(current_year, 1999, -1))
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    total_scraped = 0
    
    # We will use a session for better performance
    session = requests.Session()
    session.headers.update(headers)
    
    # Initialize last_href outside the loop
    last_href = None
    
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
            
        for year in years:
            print(f"\nScraping year: {year}")
            for group in groups:
                url = f"https://www.valueinvestorsclub.com/ideas/atoz/{group}/{year}"
                try:
                    time.sleep(2) # Increased delay to be respectful and avoid timeouts
                    response = session.get(url, timeout=30)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Based on common VIC A-Z structure, ideas are often in <li> tags or <a> within a specific div
                    # Let's find all idea links
                    idea_links = soup.find_all('a', href=re.compile(r'/idea/'))
                    
                    group_count = 0
                    for link in idea_links:
                        href = link['href']
                        text = link.get_text(strip=True)
                        
                        # In A-Z listing, "S" and "W" are icons/tags, not idea titles
                        if not text or text in ['S', 'W', 'Most Recent', 'Most Active']:
                            continue
                            
                        # Avoid duplicates within the same page parse
                        if href == last_href:
                            continue
                        last_href = href

                        # Extract position
                        is_short = False
                        # Check if 'S' sibling or parent indicator exists
                        # Often it's a sibling <span> with class 'short-icon' or text 'S'
                        prev_sibling = link.find_previous_sibling()
                        if prev_sibling and (prev_sibling.get_text(strip=True) == 'S' or 'Short' in prev_sibling.get_text()):
                            is_short = True
                        
                        # Extract ticker from text: "Company Name (TICKER) (Month YY)"
                        ticker = "Unknown"
                        company = text
                        date_str = f"{year}"
                        
                        # Use regex to find (TICKER) and (Month YY)
                        # Example: "Apple (AAPL) (Apr 25)"
                        matches = re.findall(r'\(([^)]+)\)', text)
                        if len(matches) >= 2:
                            ticker = matches[0].upper()
                            date_str = f"{matches[1]}, {year}"
                            company = text.split('(')[0].strip()
                        elif len(matches) == 1:
                            # Might be just ticker or just date
                            val = matches[0]
                            if any(m in val for m in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                                date_str = f"{val}, {year}"
                                company = text.split('(')[0].strip()
                            else:
                                ticker = val.upper()
                                company = text.split('(')[0].strip()

                        writer.writerow({
                            'ticker': ticker,
                            'company': company,
                            'position': 'SHORT' if is_short else 'LONG',
                            'date': date_str,
                            'url': f"https://www.valueinvestorsclub.com{href}"
                        })
                        group_count += 1
                        total_scraped += 1
                    
                    print(f"  Group {group}: Found {group_count} ideas")
                    csvfile.flush()
                    
                except Exception as e:
                    print(f"  Error scraping {url}: {e}")
                    
    print(f"\nScraping complete. Total ideas stored: {total_scraped}")
    return total_scraped

if __name__ == "__main__":
    scrape_vic_all_ideas()
