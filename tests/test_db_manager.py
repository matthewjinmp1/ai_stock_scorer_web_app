import os
import pytest
import sqlite3
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from utils.db_manager import DBManager

@pytest.fixture
def db():
    test_db_path = "tests/test_temp.db"
    # Ensure any old test DB is removed
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
        
    db_manager = DBManager(test_db_path)
    yield db_manager
    
    # Cleanup after tests
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

def test_save_and_get_score(db):
    ticker = "TEST"
    scores = {
        "moat_score": 7.5,
        "barriers_score": 8.0,
        "model": "test-model",
        "total_score": 75.0
    }
    company_name = "Test Company"
    
    db.save_score(ticker, scores, company_name=company_name)
    
    # Get the score back
    retrieved = db.get_score(ticker)
    
    assert retrieved is not None
    assert retrieved['ticker'] == ticker
    assert retrieved['moat_score'] == 7.5
    assert retrieved['barriers_score'] == 8.0
    assert retrieved['company_name'] == company_name
    assert retrieved['model'] == "test-model"
    assert retrieved['total_score'] == 75.0

def test_get_all_scores(db):
    db.save_score("T1", {"moat_score": 5}, "C1")
    db.save_score("T2", {"moat_score": 6}, "C2")
    
    all_scores = db.get_all_scores()
    assert len(all_scores) == 2
    assert "T1" in all_scores
    assert "T2" in all_scores
    assert all_scores["T1"]["moat_score"] == 5

def test_delete_score(db):
    db.save_score("DELETE_ME", {"moat_score": 5}, "C1")
    assert db.get_score("DELETE_ME") is not None
    
    db.delete_score("DELETE_ME")
    assert db.get_score("DELETE_ME") is None

def test_get_all_versions(db):
    ticker = "HIST"
    db.save_score(ticker, {"moat_score": 1, "model": "m1"}, "C1")
    db.save_score(ticker, {"moat_score": 2, "model": "m2"}, "C1")
    
    versions = db.get_all_versions(ticker)
    assert len(versions) == 2
    # Should be ordered by timestamp descending, so newest (m2) first
    assert versions[0]['model'] == "m2"
    assert versions[1]['model'] == "m1"

def test_clean_score_invalid_input(db):
    # Test internal _clean_score directly if possible, or through save_score
    ticker = "INVALID"
    scores = {
        "moat_score": "This is not a number",
        "barriers_score": "Score is 8.5", # Should still work and extract 8.5
        "model": "test-model",
        "total_score": "invalid"
    }
    
    db.save_score(ticker, scores)
    retrieved = db.get_score(ticker)
    
    # moat_score should be None (NULL in DB)
    assert retrieved['moat_score'] is None
    # barriers_score should be 8.5 (extracted from string)
    assert retrieved['barriers_score'] == 8.5
    # total_score should be None (NULL in DB)
    assert retrieved['total_score'] is None

