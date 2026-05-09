from app.config import Settings
from app.services.search import (
    MIN_HYBRID_SEMANTIC_SCORE,
    MIN_SEMANTIC_SCORE,
    SearchRequest,
    SearchService,
    _min_semantic_score,
)


def test_search_filters_include_attachment_filename():
    service = SearchService(Settings())
    params = {}
    filters = service._filters(SearchRequest(attachment_filename="invoice"), params)
    assert "email_attachments" in filters
    assert params["attachment_filename"] == "%invoice%"


def test_search_filters_include_recipient():
    service = SearchService(Settings())
    params = {}
    filters = service._filters(SearchRequest(recipient="kenn"), params)
    assert "email_recipients" in filters
    assert "er.kind IN ('to', 'cc', 'bcc')" in filters
    assert params["recipient"] == "%kenn%"


def test_semantic_sql_uses_vector_when_available():
    service = SearchService(Settings())
    sql = service._search_sql("contract terms", "semantic", "TRUE", has_vector=True, count=False)
    assert "sd.embedding <=>" in sql
    assert "min_semantic_score" in sql
    assert "semantic_score" in sql


def test_all_mode_uses_stricter_semantic_cutoff():
    assert _min_semantic_score("all") == MIN_HYBRID_SEMANTIC_SCORE
    assert _min_semantic_score("semantic") == MIN_SEMANTIC_SCORE
