from __future__ import annotations

from app.services import search_service


def test_shopping_search_filters_by_budget_and_returns_sources(monkeypatch):
    captured: dict = {}

    def fake_search(engine, params):
        captured.update(engine=engine, params=params)
        return {
            "shopping_results": [
                {
                    "title": "Phone A 128GB",
                    "product_link": "https://shop.example/a",
                    "source": "Store A",
                    "extracted_price": 54999,
                },
                {
                    "title": "Phone B 256GB",
                    "product_link": "https://shop.example/b",
                    "source": "Store B",
                    "extracted_price": 64999,
                },
            ]
        }

    monkeypatch.setattr(search_service.serpapi_client, "search", fake_search)
    monkeypatch.setattr(
        search_service,
        "refine_search_request",
        lambda *_: {"query": "phones under 60000 INR", "follow_up_question": "Any preferred brand?"},
    )

    result = search_service.search(
        "@Nazar phones under 60000",
        {
            "rule": {
                "query": "phones",
                "source": "shopping",
                "mode": "price_below",
                "target_price": 60000,
                "currency": "INR",
            }
        },
    )

    assert captured["engine"] == "google_shopping"
    assert captured["params"]["q"] == "phones under 60000 INR"
    assert "Phone A" in result["reply"]
    assert "₹54,999" in result["reply"]
    assert "Phone B" not in result["reply"]
    assert "Any preferred brand?" in result["reply"]
    assert result["sources"] == [{"title": "Phone A 128GB", "url": "https://shop.example/a"}]


def test_web_search_uses_serpapi_and_you_research(monkeypatch):
    calls: list[tuple[str, dict]] = []
    research_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        search_service.serpapi_client,
        "search",
        lambda engine, params: (
            calls.append((engine, params))
            or {
                "organic_results": [
                    {
                        "title": "Search result",
                        "link": "https://news.example/story",
                        "snippet": "Useful current detail",
                    }
                ]
            }
        ),
    )
    monkeypatch.setattr(
        search_service,
        "refine_search_request",
        lambda *_: {"query": "current electric vehicle incentives India", "follow_up_question": "Which state?"},
    )

    def fake_research(query, effort):
        research_calls.append((query, effort))
        return {
            "available": True,
            "content": "A sourced research summary.",
            "sources": [{"title": "Research source", "url": "https://research.example/article"}],
            "error": None,
        }

    monkeypatch.setattr(search_service.you_client, "research", fake_research)

    result = search_service.search("@Nazar EV incentives", {"rule": {"source": "web"}})

    assert calls == [
        (
            "google",
            {"q": "current electric vehicle incentives India", "hl": "en", "gl": "in", "num": 10},
        )
    ]
    assert "A sourced research summary." in result["reply"]
    assert "Useful current detail" in result["reply"]
    assert "Which state?" in result["reply"]
    assert research_calls == [("current electric vehicle incentives India", "lite")]
    assert [source["url"] for source in result["sources"]] == [
        "https://news.example/story",
        "https://research.example/article",
    ]


def test_flight_search_returns_book_action_with_google_flights_link(monkeypatch):
    captured: dict = {}

    def fake_search(engine, params):
        captured.update(engine=engine, params=params)
        return {
            "search_metadata": {"google_flights_url": "https://www.google.com/travel/flights?q=BLR-DEL"},
            "best_flights": [
                {
                    "price": 5640,
                    "total_duration": 165,
                    "flights": [
                        {
                            "airline": "IndiGo",
                            "flight_number": "6E 123",
                            "departure_airport": {"id": "BLR", "time": "08:15"},
                            "arrival_airport": {"id": "DEL", "time": "11:00"},
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(search_service.serpapi_client, "search", fake_search)
    monkeypatch.setattr(
        search_service,
        "refine_search_request",
        lambda *_: {"query": "Bangalore to Delhi flight 2026-12-25", "follow_up_question": "Prefer nonstop?"},
    )

    result = search_service.search(
        "@Nazar flight Bangalore to Delhi 25 Dec 2026",
        {
            "watch_type": "flight",
            "rule": {
                "origin": "BLR",
                "destination": "DEL",
                "travel_date": "2026-12-25",
                "currency": "INR",
                "passengers": 1,
            },
        },
    )

    assert captured["engine"] == "google_flights"
    assert captured["params"]["departure_id"] == "BLR"
    assert captured["params"]["arrival_id"] == "DEL"
    assert result["summary"].startswith("Found 1 live option")
    assert result["results"][0]["price"] == 5640
    assert result["results"][0]["action_label"] == "Book on Google Flights"
    assert result["results"][0]["url"] == "https://www.google.com/travel/flights?q=BLR-DEL"


def test_event_ticket_search_is_not_mistaken_for_a_flight(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        search_service.serpapi_client,
        "search",
        lambda engine, params: (
            captured.update(engine=engine, params=params)
            or {
                "organic_results": [
                    {
                        "title": "Concert tickets",
                        "link": "https://tickets.example/show",
                        "snippet": "Tickets available",
                    }
                ]
            }
        ),
    )
    monkeypatch.setattr(
        search_service,
        "refine_search_request",
        lambda *_: {"query": "concert tickets in Delhi", "follow_up_question": "Which date?"},
    )
    def no_research(_query, *, effort):
        assert effort == "lite"
        return {"available": False, "content": None, "sources": [], "error": None}

    monkeypatch.setattr(search_service.you_client, "research", no_research)

    result = search_service.search(
        "@Nazar concert tickets in Delhi",
        {
            "watch_type": "flight",
            "rule": {"watch_type": "flight"},
        },
    )

    assert captured["engine"] == "google"
    assert result["results"][0]["action_label"] == "View tickets"
    assert result["results"][0]["url"] == "https://tickets.example/show"


def test_exam_timetable_without_institution_asks_instead_of_guessing(monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("A timetable search needs the university before fetching results")

    monkeypatch.setattr(search_service.serpapi_client, "search", unexpected)
    monkeypatch.setattr(search_service.you_client, "research", unexpected)

    result = search_service.search(
        "@Nazar exam time table for 7th sem students",
        {"watch_type": "job_notification", "rule": {"keywords": ["exam"]}},
    )

    assert result["action"] == "search_results"
    assert result["results"] == []
    assert "university/college and branch" in result["follow_up_question"]
    assert "VTU" not in result["summary"]


def test_exam_search_filters_unrelated_results_and_uncited_research(monkeypatch):
    monkeypatch.setattr(
        search_service.serpapi_client,
        "search",
        lambda *_args, **_kwargs: {
            "organic_results": [
                {
                    "title": "VTU 7th Semester Exam Timetable",
                    "link": "https://vtu.ac.in/exams/7th-sem",
                    "snippet": "Official timetable for seventh semester.",
                },
                {
                    "title": "Secure online exams - Exam.net",
                    "link": "https://exam.net/",
                    "snippet": "Create online exams.",
                },
                {
                    "title": "VTU 6th Semester Timetable",
                    "link": "https://vtu.ac.in/exams/6th-sem",
                    "snippet": "Official sixth semester timetable.",
                },
            ]
        },
    )
    monkeypatch.setattr(
        search_service,
        "refine_search_request",
        lambda *_: {"query": "VTU 7th semester exam timetable", "follow_up_question": "Need your branch?"},
    )
    def unexpected_research(*_args, **_kwargs):
        raise AssertionError("Exam schedules should use specific search results, not an unsourced summary")

    monkeypatch.setattr(search_service.you_client, "research", unexpected_research)

    result = search_service.search(
        "@Nazar VTU exam timetable for 7th sem students",
        {"watch_type": "job_notification", "rule": {"keywords": ["exam"]}},
    )

    assert [item["title"] for item in result["results"]] == ["VTU 7th Semester Exam Timetable"]
    assert "Best match: VTU 7th Semester Exam Timetable" in result["summary"]
    assert [source["url"] for source in result["sources"]] == ["https://vtu.ac.in/exams/7th-sem"]
