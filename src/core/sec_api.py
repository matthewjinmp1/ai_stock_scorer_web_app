import os
import re
import time
import requests
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

SEC_DELAY_SECONDS = 0.12  # stay under 10 req/s
FORM_TYPES_13F = {"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"}

def _load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r") as f:
            for raw in f.readlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        return

def load_local_env() -> None:
    # Look for .env in project root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    _load_env_file(os.path.join(project_root, ".env"))

def sec_user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        ua = "AI_stock_scorer (set SEC_USER_AGENT with contact email)"
    return ua

def sec_headers(host: Optional[str] = None) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "User-Agent": sec_user_agent(),
        "Accept-Encoding": "gzip, deflate",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    if host:
        headers["Host"] = host
    return headers

def normalize_cik(cik: str) -> str:
    return str(cik).strip().zfill(10)

def cik_int_str(cik_10: str) -> str:
    return str(int(cik_10))

def accession_nodash(accession: str) -> str:
    return accession.replace("-", "")

def http_get_json(session: requests.Session, url: str, host: Optional[str] = None, timeout: int = 30) -> Any:
    time.sleep(SEC_DELAY_SECONDS)
    resp = session.get(url, headers=sec_headers(host=host), timeout=timeout)
    if resp.status_code == 403:
        raise PermissionError("SEC returned 403 Forbidden. Set SEC_USER_AGENT.")
    resp.raise_for_status()
    return resp.json()

def http_get_text(session: requests.Session, url: str, host: Optional[str] = None, timeout: int = 30) -> str:
    time.sleep(SEC_DELAY_SECONDS)
    resp = session.get(url, headers=sec_headers(host=host), timeout=timeout)
    if resp.status_code == 403:
        raise PermissionError("SEC returned 403 Forbidden. Set SEC_USER_AGENT.")
    resp.raise_for_status()
    return resp.text

def get_submissions(session: requests.Session, cik_10: str) -> Dict[str, Any]:
    url = f"https://data.sec.gov/submissions/CIK{cik_10}.json"
    return http_get_json(session, url, host=None, timeout=30)

@dataclass
class FilingRef:
    form: str
    filing_date: str
    report_date: str
    accession: str
    primary_doc: str

def extract_13f_filings(submissions: Dict[str, Any]) -> List[FilingRef]:
    recent = submissions.get("filings", {}).get("recent", {}) or {}
    forms: List[str] = recent.get("form", []) or []
    filing_dates: List[str] = recent.get("filingDate", []) or []
    report_dates: List[str] = recent.get("reportDate", []) or []
    accessions: List[str] = recent.get("accessionNumber", []) or []
    primary_docs: List[str] = recent.get("primaryDocument", []) or []

    out: List[FilingRef] = []
    for i, form in enumerate(forms):
        if form not in FORM_TYPES_13F:
            continue
        out.append(
            FilingRef(
                form=form,
                filing_date=filing_dates[i] if i < len(filing_dates) else "",
                report_date=report_dates[i] if i < len(report_dates) else "",
                accession=accessions[i] if i < len(accessions) else "",
                primary_doc=primary_docs[i] if i < len(primary_docs) else "",
            )
        )
    out.sort(key=lambda x: x.filing_date or "", reverse=True)
    return out

def filing_base_dir(cik_int: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash(accession)}"

def get_filing_index_json(session: requests.Session, subject_cik_10: str, accession: str) -> Tuple[Dict[str, Any], str]:
    subject_cik_int = cik_int_str(subject_cik_10)
    filer_cik_part = accession.split("-")[0]
    filer_cik_int = str(int(filer_cik_part))
    
    ciks_to_try = [subject_cik_int]
    if filer_cik_int not in ciks_to_try:
        ciks_to_try.append(filer_cik_int)
        
    for cik in ciks_to_try:
        base_url = filing_base_dir(cik, accession)
        url = f"{base_url}/index.json"
        try:
            data = http_get_json(session, url, host="www.sec.gov", timeout=30)
            return data, base_url
        except Exception:
            continue
    raise Exception(f"Failed to find index.json for {accession}")

def pick_info_table_file(index_json: Dict[str, Any]) -> Optional[str]:
    items = (index_json.get("directory", {}) or {}).get("item", []) or []
    filenames = [it.get("name", "") for it in items if it.get("name")]
    if not filenames: return None

    # 1. Look for XML info tables (modern format, post-2013)
    patterns = [
        r"(?i)infotable.*\.xml$",
        r"(?i)informationtable.*\.xml$",
        r"(?i)form13f.*\.xml$",
        r"(?i)holdings.*\.xml$",
        r"(?i)table.*\.xml$",
    ]
    for pat in patterns:
        for fn in filenames:
            if re.search(pat, fn): return fn
    
    # 2. Look for any XML that isn't the primary document or schema
    for fn in filenames:
        if fn.lower().endswith(".xml"):
            if any(x in fn.lower() for x in ["primary_doc", "submission", ".xsd", "filing"]): continue
            return fn
    
    # 3. Look for text-based info tables (older format, pre-2013)
    # These often have names like "d1234567_13f-hr.txt", "tech303flive.txt", or contain "13f" and ".txt"
    txt_patterns = [
        r"(?i).*13f.*\.txt$",
        r"(?i).*table.*\.txt$",
        r"(?i)infotable.*\.txt$",
        r"(?i)^tech\d+.*\.txt$",  # Old SEC format like "tech303flive.txt"
        r"(?i)^d\d+.*\.txt$",      # Document ID format like "d1382572_13f-hr.txt"
    ]
    for pat in txt_patterns:
        for fn in filenames:
            if re.search(pat, fn) and not any(x in fn.lower() for x in ["index", "header", "primary"]):
                return fn
    
    # 4. Last resort: any .txt file that's not an index or header file
    # For very old filings, they might use non-standard names
    txt_files = [f for f in filenames if f.lower().endswith(".txt")]
    non_index_txt = [f for f in txt_files if "index" not in f.lower() and "header" not in f.lower()]
    
    # If there's only one non-index .txt file, use it
    if len(non_index_txt) == 1:
        return non_index_txt[0]
    
    # If there are multiple .txt files, check if one matches the accession pattern
    # and has a corresponding index file - that's likely the main holdings document
    for fn in non_index_txt:
        # Check if there's an index file with the same base name (accession pattern)
        base_name = fn.replace('.txt', '')
        has_index = any('index' in f.lower() and base_name in f.lower() for f in filenames)
        if has_index:
            # This .txt file has a corresponding index file, so it's likely the main document
            return fn
    
    # Prefer files that look like document IDs or tech files
    for fn in non_index_txt:
        if re.search(r"^(d\d+|tech|ti\d+)", fn.lower()):
            return fn
    
    # If we still haven't found anything, return the first non-index .txt file
    if non_index_txt:
        return non_index_txt[0]
    
    return None

def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag

def parse_infotable_txt(txt_content: str) -> List[Dict[str, Any]]:
    """
    Parse text-based 13F holdings table (pre-2013 format).
    The table has fixed-width columns: NAME OF ISSUER, TITLE OF CLASS, CUSIP, VALUE, PRN AMT, etc.
    """
    holdings = []
    
    # Find the information table section
    txt_upper = txt_content.upper()
    table_start = txt_upper.find("NAME OF ISSUER")
    if table_start == -1:
        return holdings
    
    # Extract the table section
    table_section = txt_content[table_start:]
    lines = table_section.split('\n')
    
    # Find the header line to determine column positions
    header_line = None
    for line in lines[:10]:
        if 'NAME OF ISSUER' in line.upper() and 'CUSIP' in line.upper():
            header_line = line
            break
    
    if not header_line:
        return holdings
    
    # Estimate column positions based on header
    # Typical positions (approximate):
    # NAME OF ISSUER: 0-30
    # TITLE OF CLASS: 30-50
    # CUSIP: 50-60
    # VALUE: 60-75
    # PRN AMT (shares): 75-90
    # TYPE: 90-95
    # PUT/CALL: 95-100
    # DISCRETION: 100-110
    
    # Find key markers in header
    name_end = header_line.upper().find('OF CLASS')
    class_end = header_line.upper().find('CUSIP')
    cusip_end = header_line.upper().find('(X1000)') or header_line.upper().find('VALUE')
    if cusip_end == -1:
        cusip_end = class_end + 20 if class_end > 0 else 60
    
    # Process data lines
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped or len(line_stripped) < 50:
            continue
        
        # Skip header/separator lines
        if ('NAME OF ISSUER' in line.upper() or 
            '----' in line or 
            '<S>' in line or 
            '<C>' in line or
            line_stripped.replace('-', '').replace(' ', '').replace('|', '') == ''):
            continue
        
        # Extract fields using approximate positions
        issuer_name = line_stripped[:name_end].strip() if name_end > 0 else ""
        if not issuer_name or len(issuer_name) < 2:
            continue
        
        class_name = ""
        if class_end > 0 and name_end > 0:
            class_name = line_stripped[name_end:class_end].strip()
        
        # Find CUSIP (9 characters, alphanumeric, usually around position 50-60)
        cusip = ""
        cusip_start = class_end if class_end > 0 else 50
        cusip_pos = -1
        for i in range(cusip_start, min(cusip_start + 20, len(line_stripped))):
            if i + 9 <= len(line_stripped):
                candidate = line_stripped[i:i+9].strip()
                if len(candidate) == 9 and candidate.replace('-', '').isalnum():
                    cusip = candidate
                    cusip_pos = i
                    break
        
        if not cusip or cusip_pos == -1:
            continue
        
        # Extract value and shares (numeric fields after CUSIP)
        value = ""
        shares = ""
        share_type = ""
        put_call = ""
        discretion = ""
        
        # Everything after CUSIP position
        remaining = line_stripped[cusip_pos + 9:]
        # Split by whitespace but preserve structure
        parts = remaining.split()
        
        # Find numeric values - value comes first, then shares
        numeric_found = []
        for part in parts:
            clean_part = part.replace(',', '').replace('$', '').replace('(', '').replace(')', '')
            if clean_part.replace('.', '').isdigit() and len(clean_part) > 0:
                numeric_found.append(clean_part)
        
        if len(numeric_found) >= 1:
            value = numeric_found[0]
        if len(numeric_found) >= 2:
            shares = numeric_found[1]
        
        # Find share type (SH, PRN, etc.) - usually after shares
        for i, part in enumerate(parts):
            if part.upper() in ['SH', 'PRN', 'SHARES']:
                share_type = part.upper()
                break
        
        # Look for investment discretion (SOLE, SHARED, NONE)
        remaining_upper = remaining.upper()
        if 'SOLE' in remaining_upper:
            discretion = 'SOLE'
        elif 'SHARED' in remaining_upper:
            discretion = 'SHARED'
        elif 'NONE' in remaining_upper and 'NONE' not in issuer_name.upper():
            discretion = 'NONE'
        
        holdings.append({
            "nameOfIssuer": issuer_name,
            "titleOfClass": class_name,
            "cusip": cusip,
            "value": value,
            "sshPrnamt": shares,
            "sshPrnamtType": share_type or "SH",
            "putCall": put_call,
            "investmentDiscretion": discretion,
        })
    
    return holdings

def parse_infotable_xml(xml_text: str) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_text)
    info_tables: List[ET.Element] = []
    for el in root.iter():
        tag = strip_ns(el.tag).lower()
        if tag in ["infotable", "infotableentry"]:
            info_tables.append(el)
    
    if not info_tables:
        for el in root.iter():
            if strip_ns(el.tag).lower() == "infotable":
                info_tables.append(el)

    holdings: List[Dict[str, Any]] = []
    def text_of(parent: ET.Element, child_name: str) -> str:
        for ch in list(parent):
            if strip_ns(ch.tag).lower() == child_name.lower():
                return (ch.text or "").strip()
        return ""

    for it in info_tables:
        holdings.append({
            "nameOfIssuer": text_of(it, "nameOfIssuer"),
            "titleOfClass": text_of(it, "titleOfClass"),
            "cusip": text_of(it, "cusip"),
            "value": text_of(it, "value"),
            "sshPrnamt": text_of(it, "sshPrnamt"),
            "sshPrnamtType": text_of(it, "sshPrnamtType"),
            "putCall": text_of(it, "putCall"),
            "investmentDiscretion": text_of(it, "investmentDiscretion"),
        })
    return [h for h in holdings if h.get("cusip") or h.get("nameOfIssuer")]

