from toolkit.services.leads import LeadIn, enrich, payload_hash, score_lead


def test_enrich_from_website_when_free_email() -> None:
    e = enrich(LeadIn(email="bob@gmail.com", website="http://shop.example.co.uk/contact"))
    assert e.company_domain == "shop.example.co.uk"
    assert e.country == "GB"


def test_country_alias_wins_over_tld() -> None:
    e = enrich(LeadIn(email="a@firma.com.tr", country="United States"))
    assert e.country == "US"


def test_score_reasons_are_explainable() -> None:
    lead = LeadIn(email="ops@store.com", company="Store", budget_usd=1500, message="demo please")
    score = score_lead(lead, enrich(lead))
    assert score.total == 30 + 10 + 15 + 15
    assert "+15 buying intent" in score.reasons


def test_hash_ignores_email_case_and_whitespace() -> None:
    a = LeadIn(email="X@Y.com", name=" Ann ")
    b = LeadIn(email="x@y.com", name="Ann")
    assert payload_hash(a) == payload_hash(b)
