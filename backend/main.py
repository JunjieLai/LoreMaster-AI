"""
FastAPI backend for LoreMaster-AI
Provides API endpoints for the frontend including Fandom wiki image proxy
"""

import httpx
import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
from functools import lru_cache
import hashlib

# Add project root to path for imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

app = FastAPI(title="LoreMaster-AI API", version="1.0.0")

# Initialize pipeline lazily to avoid startup delays
_pipeline = None

def get_pipeline():
    """Get or create the LoreMasterPipeline singleton."""
    global _pipeline
    if _pipeline is None:
        from src.agent.pipeline import LoreMasterPipeline
        _pipeline = LoreMasterPipeline(verbose=True)
    return _pipeline

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache for thumbnails
thumbnail_cache: dict[str, Optional[str]] = {}

FANDOM_API_BASE = "https://genshin-impact.fandom.com/api.php"


class ThumbnailResponse(BaseModel):
    title: str
    thumbnail_url: Optional[str] = None
    cached: bool = False


class BatchThumbnailRequest(BaseModel):
    titles: list[str]


class BatchThumbnailResponse(BaseModel):
    thumbnails: dict[str, Optional[str]]


def normalize_title(title: str) -> str:
    """Normalize title for wiki lookup (replace spaces with underscores)"""
    return title.replace(" ", "_")


async def fetch_thumbnail_from_fandom(title: str) -> Optional[str]:
    """Fetch thumbnail URL from Fandom Wiki API"""
    normalized = normalize_title(title)

    params = {
        "action": "query",
        "titles": normalized,
        "prop": "pageimages",
        "format": "json",
        "pithumbsize": 200,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(FANDOM_API_BASE, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            pages = data.get("query", {}).get("pages", {})
            for page_id, page_data in pages.items():
                if page_id != "-1":  # -1 means page not found
                    thumbnail = page_data.get("thumbnail", {})
                    return thumbnail.get("source")

            return None
        except Exception as e:
            print(f"Error fetching thumbnail for {title}: {e}")
            return None


@app.get("/api/thumbnail/{title}", response_model=ThumbnailResponse)
async def get_thumbnail(title: str):
    """Get thumbnail URL for a single entity"""
    # Check cache first
    if title in thumbnail_cache:
        return ThumbnailResponse(
            title=title,
            thumbnail_url=thumbnail_cache[title],
            cached=True
        )

    # Fetch from Fandom API
    thumbnail_url = await fetch_thumbnail_from_fandom(title)

    # Cache the result (even if None)
    thumbnail_cache[title] = thumbnail_url

    return ThumbnailResponse(
        title=title,
        thumbnail_url=thumbnail_url,
        cached=False
    )


@app.post("/api/thumbnails/batch", response_model=BatchThumbnailResponse)
async def get_thumbnails_batch(request: BatchThumbnailRequest):
    """Get thumbnail URLs for multiple entities in batch"""
    results: dict[str, Optional[str]] = {}
    titles_to_fetch: list[str] = []

    # Check cache first
    for title in request.titles:
        if title in thumbnail_cache:
            results[title] = thumbnail_cache[title]
        else:
            titles_to_fetch.append(title)

    # Fetch missing thumbnails concurrently
    if titles_to_fetch:
        tasks = [fetch_thumbnail_from_fandom(title) for title in titles_to_fetch]
        fetched = await asyncio.gather(*tasks)

        for title, thumbnail_url in zip(titles_to_fetch, fetched):
            thumbnail_cache[title] = thumbnail_url
            results[title] = thumbnail_url

    return BatchThumbnailResponse(thumbnails=results)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "cache_size": len(thumbnail_cache)}


@app.get("/api/image-proxy")
async def proxy_image(url: str):
    """Proxy external images to avoid CORS/referrer issues"""
    from fastapi.responses import Response

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                url,
                timeout=10.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://genshin-impact.fandom.com/",
                }
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "image/png")
            return Response(
                content=response.content,
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"}
            )
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Image not found: {e}")


class QueryRequest(BaseModel):
    question: str


class SourceItem(BaseModel):
    title: str
    entity_type: str
    section: Optional[str] = None
    score: float
    text: str
    source_url: Optional[str] = None
    region: Optional[str] = None


class PathData(BaseModel):
    nodes: List[str]
    relations: List[str]
    evidences: Optional[List[str]] = None
    alternative_paths: Optional[List[Dict[str, Any]]] = None


class TimingData(BaseModel):
    total: float
    retrieval: Optional[float] = None
    generation: Optional[float] = None


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    entities: List[str]
    query_type: str
    path: Optional[PathData] = None
    timing: TimingData
    cost: float


class GraphNodeModel(BaseModel):
    id: str
    name: str
    type: str


class GraphLinkModel(BaseModel):
    source: str
    target: str
    relation: str


class GraphExportResponse(BaseModel):
    nodes: List[GraphNodeModel]
    links: List[GraphLinkModel]
    stats: Dict[str, Any]


@app.get("/api/graph", response_model=GraphExportResponse)
async def get_full_graph():
    """Export the full knowledge graph from Neo4j for visualization."""
    try:
        pipeline = get_pipeline()
        driver = pipeline.retriever.driver

        with driver.session() as session:
            nodes_result = session.run(
                "MATCH (e:Entity) RETURN e.name AS name, e.type AS type ORDER BY e.name"
            )
            nodes = [
                GraphNodeModel(id=r["name"], name=r["name"], type=r["type"] or "default")
                for r in nodes_result
            ]

            links_result = session.run(
                "MATCH (s:Entity)-[r]->(t:Entity) "
                "RETURN s.name AS source, type(r) AS relation, t.name AS target"
            )
            links = [
                GraphLinkModel(source=r["source"], target=r["target"], relation=r["relation"])
                for r in links_result
            ]

        type_counts: Dict[str, int] = {}
        for node in nodes:
            type_counts[node.type] = type_counts.get(node.type, 0) + 1

        relation_counts: Dict[str, int] = {}
        for link in links:
            relation_counts[link.relation] = relation_counts.get(link.relation, 0) + 1

        return GraphExportResponse(
            nodes=nodes,
            links=links,
            stats={
                "total_nodes": len(nodes),
                "total_links": len(links),
                "by_type": type_counts,
                "by_relation": relation_counts,
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Graph export error: {str(e)}")


@app.post("/api/query", response_model=QueryResponse)
async def query_loremaster(request: QueryRequest):
    """
    Query the LoreMaster AI agent.

    This endpoint processes a natural language question about Genshin Impact lore
    and returns an answer with sources, entity information, and relationship paths.
    """
    try:
        pipeline = get_pipeline()
        result = pipeline.answer(request.question)

        # Map vector results to source items with full details
        sources = []
        for r in result.get("_vector_results", []):
            source = SourceItem(
                title=r.get("title", "Unknown"),
                entity_type=r.get("entity_type", "Lore"),
                section=r.get("section_title"),
                score=r.get("score", 0.0),
                text=r.get("full_text", "")[:500],  # Truncate for response
                source_url=r.get("source_url"),
                region=r.get("regions", [None])[0] if r.get("regions") else None,
            )
            sources.append(source)

        # If no vector results stored, use the basic sources
        if not sources and result.get("sources"):
            for s in result["sources"]:
                sources.append(SourceItem(
                    title=s.get("title", "Unknown"),
                    entity_type="Lore",
                    score=s.get("score", 0.0),
                    text="",
                ))

        # Build path data if available
        path = None
        if result.get("path"):
            path_data = result["path"]
            if isinstance(path_data, dict):
                path = PathData(
                    nodes=path_data.get("nodes", []),
                    relations=path_data.get("relations", []),
                    evidences=path_data.get("evidences"),
                    alternative_paths=path_data.get("alternative_paths"),
                )
            elif isinstance(path_data, list):
                # path_steps format - parse it
                nodes = []
                relations = []
                for step in path_data:
                    parts = step.split(" -[")
                    if parts:
                        if not nodes:
                            nodes.append(parts[0])
                        if len(parts) > 1:
                            rel_target = parts[1].split("]-> ")
                            if len(rel_target) >= 2:
                                relations.append(rel_target[0])
                                nodes.append(rel_target[1])
                if nodes and relations:
                    path = PathData(nodes=nodes, relations=relations)

        # Build timing data
        timing_raw = result.get("timing", {})
        timing = TimingData(
            total=timing_raw.get("total", 0.0),
            retrieval=timing_raw.get("retrieval"),
            generation=timing_raw.get("answer_generation"),
        )

        # Get cost
        usage = result.get("usage", {})
        cost = usage.get("cost_usd", 0.0)

        return QueryResponse(
            answer=result.get("answer", ""),
            sources=sources,
            entities=result.get("entities", []),
            query_type=result.get("query_type", "FACTUAL"),
            path=path,
            timing=timing,
            cost=cost,
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
