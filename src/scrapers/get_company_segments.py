#!/usr/bin/env python3
"""
Fetch company business segments from Wikipedia.
Wikipedia is a free, open-source that provides detailed information about
company operations and business segments.
"""

import requests
import json
import re
import sys
from bs4 import BeautifulSoup
from typing import List, Dict, Optional


def search_wikipedia_for_company(company_name: str) -> Optional[str]:
    """
    Search Wikipedia for a company page, handling disambiguation.
    Returns the best matching company page title.
    """
    # Use Wikipedia search API
    search_url = "https://en.wikipedia.org/w/api.php"
    params = {
        'action': 'opensearch',
        'search': company_name,
        'limit': 10,
        'namespace': 0,
        'format': 'json'
    }
    
    try:
        response = requests.get(search_url, params=params, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        data = response.json()
        
        # data[1] contains the page titles, data[3] contains URLs
        titles = data[1] if len(data) > 1 else []
        
        # Look for company-related pages
        company_keywords = ['(company)', '(corporation)', 'inc.', 'inc', 'corp', 'corp.', 'ltd', 'ltd.']
        
        # First, try to find pages with company indicators
        for title in titles:
            title_lower = title.lower()
            if any(keyword in title_lower for keyword in company_keywords):
                return title
        
        # If no company indicator found, try to find pages that mention business terms
        # Use the search API to get more context
        for title in titles[:5]:  # Check first 5 results
            # Get summary to check if it's about a company
            summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
            try:
                summary_response = requests.get(summary_url, headers={'User-Agent': 'Mozilla/5.0'})
                if summary_response.status_code == 200:
                    summary_data = summary_response.json()
                    extract = summary_data.get('extract', '').lower()
                    # Check for business/company indicators
                    business_terms = ['company', 'corporation', 'multinational', 'technology', 
                                     'business', 'founded', 'headquartered', 'revenue', 'stock']
                    if any(term in extract for term in business_terms):
                        return title
            except:
                continue
        
        # If still nothing, return the first result (might be the company)
        if titles:
            return titles[0]
        
        return None
        
    except Exception as e:
        return None


def is_disambiguation_page(summary_text: str) -> bool:
    """Check if a Wikipedia page is a disambiguation page."""
    if not summary_text:
        return False
    
    disambiguation_indicators = [
        'most often refers to',
        'may refer to',
        'commonly refers to',
        'disambiguation',
        'usually refers to'
    ]
    
    summary_lower = summary_text.lower()
    return any(indicator in summary_lower for indicator in disambiguation_indicators)


def get_company_segments_from_wikipedia(company_name: str) -> Dict[str, any]:
    """
    Fetch company business segments from Wikipedia.
    
    Args:
        company_name: Name of the company (e.g., "Google", "Alphabet Inc.")
        
    Returns:
        Dictionary with company info and segments
    """
    # Wikipedia API endpoint
    api_url = "https://en.wikipedia.org/api/rest_v1/page/summary/"
    
    # For common ambiguous names, try with "(company)" suffix first
    ambiguous_names = ['amazon', 'apple', 'target', 'shell', 'tesla', 'nike', 'adidas']
    original_name = company_name
    if company_name.lower() in ambiguous_names and "(company)" not in company_name.lower():
        # Try with (company) suffix first
        company_name_with_suffix = f"{company_name} (company)"
        url_name = company_name_with_suffix.replace(" ", "_")
        try:
            test_response = requests.get(f"{api_url}{url_name}", 
                                      headers={'User-Agent': 'Mozilla/5.0'})
            if test_response.status_code == 200:
                company_name = company_name_with_suffix
        except:
            pass
    
    # Clean company name for URL
    url_name = company_name.replace(" ", "_")
    
    # Store original name for display
    display_name = original_name
    
    result = {
        "company_name": display_name,
        "segments": [],
        "description": "",
        "source": "Wikipedia",
        "url": f"https://en.wikipedia.org/wiki/{url_name}"
    }
    
    try:
        # Get page summary
        response = requests.get(f"{api_url}{url_name}", 
                              headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        summary_data = response.json()
        
        summary_text = summary_data.get("extract", "")
        result["description"] = summary_text
        
        # Check if this is a disambiguation page
        if is_disambiguation_page(summary_text):
            # Search for the company page (use original name for search)
            print(f"  Detected disambiguation page. Searching for company page...")
            company_page = search_wikipedia_for_company(original_name)
            
            if company_page and company_page != url_name:
                print(f"  Found company page: {company_page}")
                # Update to use the company page
                url_name = company_page.replace(" ", "_")
                # Keep original display name but update URL
                result["url"] = f"https://en.wikipedia.org/wiki/{url_name}"
                
                # Fetch the correct page
                response = requests.get(f"{api_url}{url_name}", 
                                      headers={'User-Agent': 'Mozilla/5.0'})
                response.raise_for_status()
                summary_data = response.json()
                summary_text = summary_data.get("extract", "")
                result["description"] = summary_text
        
        # Now get full page content to extract segments
        content_url = f"https://en.wikipedia.org/api/rest_v1/page/html/{url_name}"
        content_response = requests.get(content_url,
                                       headers={'User-Agent': 'Mozilla/5.0'})
        content_response.raise_for_status()
        
        # Parse HTML to find business segments
        soup = BeautifulSoup(content_response.text, 'html.parser')
        segments = extract_segments_from_html(soup, company_name)
        
        # Also try to extract from summary (often more reliable)
        summary_segments = extract_segments_from_summary(summary_text)
        
        # Combine and deduplicate
        all_segments = segments + summary_segments
        # Remove duplicates while preserving order
        seen = set()
        unique_segments = []
        for seg in all_segments:
            seg = seg.strip()
            seg_lower = seg.lower()
            # Filter out segments that are too long (likely concatenated) or contain irrelevant info
            if (seg_lower and seg_lower not in seen and len(seg) > 3 and len(seg) < 80 and
                not any(x in seg_lower for x in ['full list', 'see also', 'references', 's&p', 'nasdaq-100', 'nyse'])):
                # Check if it looks like concatenated words (no spaces and very long)
                if len(seg) > 20 and ' ' not in seg:
                    continue  # Skip concatenated segments
                seen.add(seg_lower)
                unique_segments.append(seg)
        
        if unique_segments:
            result["segments"] = unique_segments[:20]
    
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            result["error"] = f"Wikipedia page not found for '{company_name}'"
        else:
            result["error"] = f"Error fetching from Wikipedia: {e}"
    except Exception as e:
        result["error"] = f"Error: {e}"
    
    return result


def extract_segments_from_html(soup: BeautifulSoup, company_name: str) -> List[str]:
    """Extract business segments from Wikipedia HTML."""
    segments = []
    
    # Look for common section headings related to business segments
    segment_keywords = [
        "products and services",
        "business segments",
        "divisions",
        "operations",
        "services",
        "products"
    ]
    
    # Find all headings - Wikipedia uses span.mw-headline inside headings
    headings = soup.find_all(['h2', 'h3'])
    
    for heading in headings:
        heading_text = heading.get_text().lower().strip()
        
        # Check if this heading is about business segments
        if any(keyword in heading_text for keyword in segment_keywords):
            # Get the parent section
            section = heading.find_next_sibling(['div', 'ul', 'p', 'section'])
            if not section:
                # Try finding parent and then next sibling
                parent = heading.parent
                if parent:
                    section = parent.find_next_sibling(['div', 'ul', 'p', 'section'])
            
            if section:
                # Extract list items (most common format)
                items = section.find_all('li', recursive=True)
                if not items:
                    # Try paragraphs
                    items = section.find_all('p', recursive=True)
                
                for item in items[:15]:  # Limit items per section
                    text = item.get_text().strip()
                    if text and len(text) > 5 and len(text) < 150:
                        # Clean up the text
                        text = re.sub(r'\[.*?\]', '', text)  # Remove citations
                        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
                        text = text.strip()
                        # Only add if it looks like a business segment (not too long, has some structure)
                        if text and not text.startswith('See also') and not text.startswith('References'):
                            segments.append(text)
    
    # Check infobox for industry/products/services
    infobox = soup.find('table', class_=lambda x: x and 'infobox' in str(x).lower())
    if infobox:
        rows = infobox.find_all('tr')
        for row in rows:
            header = row.find('th')
            if header:
                header_text = header.get_text().lower().strip()
                if any(keyword in header_text for keyword in ['products', 'services', 'industry']):
                    data = row.find('td')
                    if data:
                        text = data.get_text().strip()
                        # Clean up
                        text = re.sub(r'\[.*?\]', '', text)
                        text = re.sub(r'\s+', ' ', text)
                        if text and len(text) < 200:
                            segments.append(text)
    
    return segments


def extract_segments_from_summary(summary_text: str) -> List[str]:
    """Extract business segments from Wikipedia summary text."""
    segments = []
    
    # Pattern 1: "focused on X, Y, Z, and W" - very common pattern
    pattern1 = r'(?:focused on|focuses on|provides|offers|operates in|produces|develops|manufactures|specializes in)\s+([^.]{10,400})'
    matches = re.finditer(pattern1, summary_text, re.IGNORECASE)
    for match in matches:
        text = match.group(1)
        # Split by commas and "and"
        parts = re.split(r',\s*|\s+and\s+', text)
        for part in parts:
                part = part.strip()
                # Remove trailing phrases like "(AI)" or citations
                part = re.sub(r'\s*\([^)]*\)\s*$', '', part)
                part = re.sub(r'\.$', '', part)
                # Remove leading "and" or "or"
                part = re.sub(r'^(and|or)\s+', '', part, flags=re.IGNORECASE)
                # Clean up
                if part and len(part) > 3 and len(part) < 80:
                    # Capitalize first letter of each word for consistency
                    part = ' '.join(word.capitalize() for word in part.split())
                    segments.append(part)
    
    # Pattern 2: Look for lists after "including" or "such as"
    pattern2 = r'(?:including|such as|like)\s+([^.]{10,200})'
    matches = re.finditer(pattern2, summary_text, re.IGNORECASE)
    for match in matches:
        text = match.group(1)
        parts = re.split(r'[,;]|\sand\s', text)
        for part in parts:
            part = part.strip()
            part = re.sub(r'\s*\([^)]*\)\s*$', '', part)
            part = re.sub(r'\.$', '', part)
            if part and len(part) > 3 and len(part) < 80:
                part = ' '.join(word.capitalize() for word in part.split())
                segments.append(part)
    
    # Pattern 3: Look for common business segment keywords mentioned in the text
    # This helps catch segments even if they're not in a list format
    keywords = [
        'search engine', 'search engine technology', 'digital advertising', 'online advertising',
        'cloud computing', 'software', 'hardware', 'consumer electronics', 
        'e-commerce', 'artificial intelligence', 'machine learning', 
        'mobile operating system', 'web browser', 'email', 'productivity software',
        'video streaming', 'social media', 'gaming', 'enterprise software',
        'data analytics', 'cybersecurity', 'fintech', 'quantum computing',
        'information technology', 'advertising technology'
    ]
    
    summary_lower = summary_text.lower()
    for keyword in keywords:
        if keyword in summary_lower:
            # Format nicely
            formatted = ' '.join(word.capitalize() for word in keyword.split())
            segments.append(formatted)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_segments = []
    for seg in segments:
        seg_lower = seg.lower().strip()
        if seg_lower and seg_lower not in seen:
            seen.add(seg_lower)
            unique_segments.append(seg)
    
    return unique_segments[:20]


def get_segments_for_ticker(ticker: str) -> Optional[Dict[str, any]]:
    """
    Get company segments using ticker symbol.
    First tries to get company name, then fetches segments.
    """
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.info
        company_name = info.get('longName') or info.get('shortName') or info.get('name')
        
        if not company_name:
            return None
        
        # Sometimes yfinance returns names like "Alphabet Inc." but Wikipedia uses "Alphabet"
        # Try the company name first, then try variations
        variations = [
            company_name,
            company_name.replace(" Inc.", "").replace(" Inc", ""),
            company_name.replace(" Corporation", "").replace(" Corp.", "").replace(" Corp", ""),
            company_name.split("(")[0].strip() if "(" in company_name else company_name
        ]
        
        for name in variations:
            result = get_company_segments_from_wikipedia(name)
            if "error" not in result or "not found" not in result.get("error", ""):
                result["ticker"] = ticker
                return result
        
        return result
        
    except Exception as e:
        return {"error": f"Error getting company name for ticker {ticker}: {e}"}


def print_segments(result: Dict[str, any]):
    """Pretty print the segments information."""
    print("\n" + "=" * 80)
    print(f"Company: {result.get('company_name', 'Unknown')}")
    if 'ticker' in result:
        print(f"Ticker: {result['ticker']}")
    print(f"Source: {result.get('source', 'Unknown')}")
    print("=" * 80)
    
    if "error" in result:
        print(f"\n[ERROR] {result['error']}")
        return
    
    if result.get('description'):
        print(f"\nDescription:")
        print(f"{result['description'][:500]}...")
    
    segments = result.get('segments', [])
    if segments:
        print(f"\nBusiness Segments ({len(segments)} found):")
        print("-" * 80)
        for i, segment in enumerate(segments, 1):
            print(f"  {i}. {segment}")
    else:
        print("\n[WARNING] No specific business segments found in structured format.")
        print("   The description above may contain segment information.")
    
    if result.get('url'):
        print(f"\nSource URL: {result['url']}")
    print()


def process_company_input(user_input: str):
    """Process a single company name or ticker input."""
    if not user_input:
        print("Error: No company name or ticker provided.")
        return
    
    # Check if input looks like a ticker (short, uppercase, alphanumeric)
    is_ticker = len(user_input) <= 5 and user_input.isalnum() and user_input.isupper()
    
    if is_ticker:
        # Try as ticker first
        print(f"Fetching business segments for ticker: {user_input}...")
        result = get_segments_for_ticker(user_input)
        
        if result and "error" not in result:
            print_segments(result)
        else:
            # If ticker lookup fails, try as company name
            print(f"\nTicker lookup failed, trying as company name: {user_input}...")
            result = get_company_segments_from_wikipedia(user_input)
            print_segments(result)
    else:
        # Treat as company name
        print(f"Fetching business segments for: {user_input}...")
        result = get_company_segments_from_wikipedia(user_input)
        print_segments(result)


if __name__ == "__main__":
    # If command-line argument provided, run once and exit
    if len(sys.argv) > 1:
        user_input = sys.argv[1]
        process_company_input(user_input)
    else:
        # Interactive mode: loop until user quits
        print("Company Business Segments Lookup")
        print("Enter company names or ticker symbols (type 'quit' or 'exit' to stop)")
        print("-" * 80)
        
        while True:
            try:
                user_input = input("\nEnter company name or ticker symbol: ").strip()
                
                # Check for quit commands
                if user_input.lower() in ['quit', 'exit', 'q', '']:
                    print("\nGoodbye!")
                    break
                
                process_company_input(user_input)
                
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except EOFError:
                print("\n\nGoodbye!")
                break
