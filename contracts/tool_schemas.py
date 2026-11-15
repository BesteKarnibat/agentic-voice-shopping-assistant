"""
Tool contracts for the MCP server.

Owner: Juan (MCP server). Akshaj implements the search behind rag.search.
Devanshu's Retriever node calls these tools. Change only after telling the team.

Pydantic models give you JSON schemas for free, which you need for MCP tool
discovery. Run `python -m contracts.tool_schemas` to export tool_schemas.json.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# rag.search  (private Amazon catalog)
# ---------------------------------------------------------------------------


class RagSearchInput(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language search text, e.g. 'eco-friendly stainless steel cleaner'.")
    top_k: int = Field(5, ge=1, le=20, description="Number of products to return.")
    category: Optional[str] = Field(None, description="Exact category filter, e.g. 'Household Cleaning'.")
    brand: Optional[str] = Field(None, description="Brand filter (case-insensitive).")
    min_price: Optional[float] = Field(None, ge=0, description="Minimum price in USD.")
    max_price: Optional[float] = Field(None, ge=0, description="Maximum price in USD.")
    min_rating: Optional[float] = Field(None, ge=0, le=5, description="Minimum star rating.")
    exclude_ingredients: list[str] = Field(default_factory=list, description="Drop products containing any of these.")


class RagProduct(BaseModel):
    """One catalog product. Mirrors the columns of products.parquet."""
    doc_id: str = Field(..., description="Stable citation ID, e.g. 'amz-000123'. Never changes between index rebuilds.")
    sku: Optional[str] = Field(None, description="Original Amazon ID/ASIN if the dataset has one.")
    title: str
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = Field(None, description="Catalog price in USD. None if missing in the dataset.")
    size_value: Optional[float] = Field(None, description="Package size, e.g. 16.0")
    size_unit: Optional[str] = Field(None, description="Normalized unit, e.g. 'oz'.")
    price_per_unit: Optional[float] = Field(None, description="price / size_value, for fair comparison.")
    rating: Optional[float] = Field(None, ge=0, le=5)
    ingredients: Optional[list[str]] = Field(None, description="None means unknown, not 'no ingredients'.")
    features_snippet: Optional[str] = Field(None, description="Short excerpt used as evidence for the answer.")
    score: float = Field(..., description="Retrieval relevance score (higher is better).")


class RagSearchOutput(BaseModel):
    query: str
    filters_applied: dict
    results: list[RagProduct]
    took_ms: int


# ---------------------------------------------------------------------------
# web.search  (live web via Brave / Serper / Bing)
# ---------------------------------------------------------------------------


class WebSearchInput(BaseModel):
    query: str = Field(..., min_length=1, description="Search text, e.g. 'Brand X steel cleaner price'.")
    max_results: int = Field(5, ge=1, le=10)


class WebResult(BaseModel):
    title: str
    url: str = Field(..., description="Source URL. Required: every live fact must be citable.")
    snippet: str
    source_domain: str = Field(..., description="e.g. 'walmart.com'. Used for domain allow-listing.")
    price: Optional[float] = Field(None, description="Parsed USD price if found in the result, else None.")
    availability: Optional[Literal["in_stock", "out_of_stock", "unknown"]] = None


class WebSearchOutput(BaseModel):
    query: str
    provider: str = Field(..., description="'brave', 'serper', ...")
    cached: bool = Field(..., description="True if served from the TTL cache.")
    retrieved_at: datetime
    results: list[WebResult]


# ---------------------------------------------------------------------------
# Tool registry: what MCP discovery should advertise
# ---------------------------------------------------------------------------

TOOLS = {
    "rag.search": {
        "description": "Search the private Amazon product catalog with semantic search plus metadata filters. "
                       "Use for product facts. Returns doc_id for citations.",
        "input": RagSearchInput,
        "output": RagSearchOutput,
    },
    "web.search": {
        "description": "Search the live web for current prices or availability. "
                       "Use only when the user asks for current/latest/in-stock info or catalog data is missing.",
        "input": WebSearchInput,
        "output": WebSearchOutput,
    },
}


def export_json_schemas(path: str = "tool_schemas.json") -> dict:
    schemas = {
        name: {
            "description": spec["description"],
            "inputSchema": spec["input"].model_json_schema(),
            "outputSchema": spec["output"].model_json_schema(),
        }
        for name, spec in TOOLS.items()
    }
    with open(path, "w") as f:
        json.dump(schemas, f, indent=2)
    return schemas


if __name__ == "__main__":
    export_json_schemas()
    print("Wrote tool_schemas.json")
