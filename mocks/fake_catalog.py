"""Fake Toys & Games data for the mock MCP server (not real catalog rows).

Test scenarios: amz-fake-006 has a price conflict, amz-fake-001 matches by SKU,
amz-fake-002 is out of stock.
"""

from __future__ import annotations

import re

FAKE_PRODUCTS: list[dict] = [
    {"doc_id": "amz-fake-001", "sku": "B00NHQFA1I", "title": "LEGO Classic Medium Creative Brick Box 10696 Building Kit (484 Pieces)",
     "brand": "LEGO", "category": "Toys & Games | Building Toys | Building Sets", "price": 34.99, "rating": 4.8,
     "min_age_years": 4, "max_age_years": 99, "safety_warnings": ["choking hazard: small parts"],
     "features_snippet": "484 colorful LEGO bricks in 35 colors with ideas booklet; storage box included."},
    {"doc_id": "amz-fake-002", "sku": "B0002TV2LU", "title": "Ticket to Ride Board Game - Train Route Strategy Game for Family",
     "brand": "Days of Wonder", "category": "Toys & Games | Games | Board Games", "price": 44.99, "rating": 4.8,
     "min_age_years": 8, "max_age_years": None, "safety_warnings": ["choking hazard: small parts"],
     "features_snippet": "2-5 players, 30-60 minute family strategy board game about building train routes."},
    {"doc_id": "amz-fake-003", "sku": "B000068CKY", "title": "Melissa & Doug Shape Sorting Cube Wooden Toddler Toy",
     "brand": "Melissa & Doug", "category": "Toys & Games | Baby & Toddler Toys | Sorting & Stacking Toys", "price": 14.99,
     "rating": 4.7, "min_age_years": 2, "max_age_years": 4, "safety_warnings": None,
     "features_snippet": "Wooden cube with 12 chunky shapes for sorting; builds shape recognition."},
    {"doc_id": "amz-fake-004", "sku": "B00004TZY8", "title": "UNO Card Game for Family Night",
     "brand": "Mattel Games", "category": "Toys & Games | Games | Card Games", "price": 5.99, "rating": 4.8,
     "min_age_years": 7, "max_age_years": None, "safety_warnings": None,
     "features_snippet": "Classic matching card game for 2-10 players; 112 cards."},
    {"doc_id": "amz-fake-005", "sku": "B07FKMZ3KJ", "title": "Ravensburger Disney Castle 1000 Piece Jigsaw Puzzle for Adults",
     "brand": "Ravensburger", "category": "Toys & Games | Puzzles | Jigsaw Puzzles", "price": 19.99, "rating": 4.7,
     "min_age_years": 12, "max_age_years": None, "safety_warnings": None,
     "features_snippet": "1000 pieces, anti-glare linen finish, finished size 27 x 20 inches."},
    {"doc_id": "amz-fake-006", "sku": "B00EDLFH8C", "title": "Hasbro Gaming Monopoly Classic Board Game for Families",
     "brand": "Hasbro Gaming", "category": "Toys & Games | Games | Board Games", "price": 19.99, "rating": 4.6,
     "min_age_years": 8, "max_age_years": None, "safety_warnings": ["choking hazard: small parts"],
     "features_snippet": "Classic property trading family board game for 2-8 players."},
    {"doc_id": "amz-fake-007", "sku": "B0015KN2EE", "title": "Fisher-Price Rock-a-Stack Baby Stacking Toy",
     "brand": "Fisher-Price", "category": "Toys & Games | Baby & Toddler Toys | Sorting & Stacking Toys", "price": 6.99,
     "rating": 4.8, "min_age_years": 0.5, "max_age_years": 3, "safety_warnings": None,
     "features_snippet": "Five colorful rings and a rocking base; for babies 6 months and up."},
    {"doc_id": "amz-fake-008", "sku": "B00008BFZH", "title": "Snap Circuits Jr. SC-100 Electronics Exploration Kit STEM Toy",
     "brand": "Elenco", "category": "Toys & Games | Learning & Education | Science Kits", "price": 29.99, "rating": 4.8,
     "min_age_years": 8, "max_age_years": None, "safety_warnings": ["choking hazard: small parts", "adult supervision recommended"],
     "features_snippet": "Over 100 STEM electronics projects with snap-together parts; no soldering."},
    {"doc_id": "amz-fake-009", "sku": "B000CBSNKQ", "title": "Magna-Tiles Clear Colors 32 Piece Magnetic Building Tiles",
     "brand": "Magna-Tiles", "category": "Toys & Games | Building Toys | Magnetic Building", "price": 49.99, "rating": 4.9,
     "min_age_years": 3, "max_age_years": None, "safety_warnings": ["contains magnets", "choking hazard: small parts"],
     "features_snippet": "32 translucent magnetic tiles for open-ended STEM building play."},
    {"doc_id": "amz-fake-010", "sku": "B010TQY7A8", "title": "Exploding Kittens Card Game - Family-Friendly Party Game",
     "brand": "Exploding Kittens", "category": "Toys & Games | Games | Card Games", "price": 19.99, "rating": 4.8,
     "min_age_years": 7, "max_age_years": None, "safety_warnings": None,
     "features_snippet": "Strategic kitty-powered card game for 2-5 players; 15 minute rounds."},
    {"doc_id": "amz-fake-011", "sku": "B00D8STBHY", "title": "Hasbro Gaming Connect 4 Classic Grid Strategy Board Game",
     "brand": "Hasbro Gaming", "category": "Toys & Games | Games | Board Games", "price": 9.99, "rating": 4.8,
     "min_age_years": 6, "max_age_years": None, "safety_warnings": ["choking hazard: small parts"],
     "features_snippet": "Two-player strategy game: line up four checkers in a row to win."},
    {"doc_id": "amz-fake-012", "sku": "B00000IZJB", "title": "Catan Board Game (Base Game) Strategy Game for Adults and Family",
     "brand": "Catan Studio", "category": "Toys & Games | Games | Board Games", "price": 43.99, "rating": 4.8,
     "min_age_years": 10, "max_age_years": None, "safety_warnings": ["choking hazard: small parts"],
     "features_snippet": "Trade, build and settle; 3-4 players, 60-90 minutes."},
]

FAKE_WEB_RESULTS: list[dict] = [
    {"title": "Hasbro Gaming Monopoly Classic Board Game - Walmart.com",
     "url": "https://www.walmart.com/ip/monopoly-classic-board-game/12345678",
     "snippet": "Monopoly Classic family board game, ages 8+. Current price $24.97.",
     "source_domain": "walmart.com", "price": 24.97, "availability": "in_stock"},
    {"title": "LEGO Classic Medium Creative Brick Box 10696 : Amazon.com",
     "url": "https://www.amazon.com/dp/B00NHQFA1I",
     "snippet": "LEGO Classic Medium Creative Brick Box 10696, 484 pieces. $34.99 in stock.",
     "source_domain": "amazon.com", "price": 34.99, "availability": "in_stock"},
    {"title": "Ticket to Ride Board Game : Target",
     "url": "https://www.target.com/p/ticket-to-ride-board-game/-/A-11111111",
     "snippet": "Ticket to Ride by Days of Wonder. Out of stock at most stores. $54.99.",
     "source_domain": "target.com", "price": 54.99, "availability": "out_of_stock"},
    {"title": "Connect 4 Classic Grid Board Game by Hasbro Gaming - Target",
     "url": "https://www.target.com/p/connect-4-classic-grid/-/A-22222222",
     "snippet": "Hasbro Gaming Connect 4 strategy board game. $9.49, available for pickup today.",
     "source_domain": "target.com", "price": 9.49, "availability": "in_stock"},
    {"title": "UNO Card Game - Walmart.com",
     "url": "https://www.walmart.com/ip/uno-card-game/33333333",
     "snippet": "Mattel Games UNO classic card game for family night, $5.97.",
     "source_domain": "walmart.com", "price": 5.97, "availability": "in_stock"},
    {"title": "Snap Circuits Jr. SC-100 Electronics Kit : Amazon.com",
     "url": "https://www.amazon.com/dp/B00008BFZH",
     "snippet": "Elenco Snap Circuits Jr. SC-100 STEM kit, 100+ projects. $31.49.",
     "source_domain": "amazon.com", "price": 31.49, "availability": "in_stock"},
    {"title": "The best family board games of the year | Wirecutter",
     "url": "https://www.nytimes.com/wirecutter/reviews/best-family-board-games/",
     "snippet": "Our favorite board games for families, from Ticket to Ride to Catan.",
     "source_domain": "nytimes.com", "price": None, "availability": None},
]

_STOP = {"the", "and", "for", "with", "a", "an", "of", "to", "in", "on", "my", "me", "i", "is", "are",
         "under", "over", "price", "current", "now", "best", "good", "some", "find", "recommend", "want",
         "need", "year", "years", "old", "kid", "kids", "child", "toy", "toys", "game", "games"}


def tokens(text: str | None) -> set[str]:
    """Lower-case word tokens with naive plural stripping."""
    out = set()
    for t in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if len(t) > 4 and t.endswith("ies"):
            t = t[:-3] + "y"
        elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.add(t)
    return out


def _content_tokens(text: str) -> set[str]:
    return {t for t in tokens(text) if t not in _STOP and len(t) > 1}


def fake_rag_search(query: str, top_k: int = 5, category=None, brand=None, min_price=None, max_price=None,
                    min_rating=None, child_age_years=None, exclude_features=()) -> list[dict]:
    """Keyword overlap + metadata filters over FAKE_PRODUCTS."""
    q = _content_tokens(query)
    q_all = {t for t in tokens(query) if t not in {"the", "and", "for", "a", "an", "my", "under", "price"}}
    hits = []
    for p in FAKE_PRODUCTS:
        if category and category.lower() not in (p["category"] or "").lower():
            continue
        if brand and brand.lower() not in (p["brand"] or "").lower():
            continue
        price = p["price"]
        if min_price is not None and (price is None or price < min_price):
            continue
        if max_price is not None and (price is None or price > max_price):
            continue
        if min_rating is not None and (p["rating"] or 0) < min_rating:
            continue
        if child_age_years is not None and p["min_age_years"] is not None and p["min_age_years"] > child_age_years:
            continue
        haystack = " ".join([p["title"], p["category"] or "", p["features_snippet"] or "",
                             " ".join(p["safety_warnings"] or [])]).lower()
        if any(f.lower() in haystack for f in exclude_features or ()):
            continue
        doc = tokens(" ".join([p["title"], p["brand"] or "", p["category"] or "", p["features_snippet"] or ""]))
        strong = len(q & doc)
        weak = len(q_all & doc)
        if strong == 0 and (q or weak == 0):
            continue
        score = round((strong * 2 + weak) / (2 * max(len(q), 1) + max(len(q_all), 1)), 3)
        hits.append({**p, "score": score})
    hits.sort(key=lambda h: (-h["score"], -(h["rating"] or 0)))
    return hits[:top_k]


def fake_web_search(query: str, max_results: int = 5) -> list[dict]:
    """Fake live results sharing at least two content words with the query."""
    q = _content_tokens(query)
    scored = []
    for r in FAKE_WEB_RESULTS:
        overlap = len(q & _content_tokens(r["title"] + " " + r["snippet"]))
        if overlap >= 2 or (overlap == 1 and len(q) == 1):
            scored.append((overlap, r))
    scored.sort(key=lambda x: -x[0])
    return [dict(r) for _, r in scored[:max_results]]
