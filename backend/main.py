"""
FastAPI backend for LoreMaster-AI

Optimizations applied:
- @app.on_event("startup"): pre-warms pipeline + DynamoDB caches (eliminates cold-start)
- run_in_executor: sync pipeline runs in thread pool, event loop stays free for concurrency
- /api/query/stream: SSE streaming endpoint, TTFB <500ms
- Session support: optional session_id for multi-turn conversation memory
"""

import asyncio
import httpx
import json
import logging
import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="LoreMaster-AI API", version="2.0.0")

# Pipeline singleton — initialized at startup, not on first request
_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        from src.agent.pipeline import LoreMasterPipeline
        _pipeline = LoreMasterPipeline(verbose=True)
    return _pipeline


# CORS
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

# In-memory thumbnail cache
thumbnail_cache: dict[str, Optional[str]] = {}
FANDOM_API_BASE = "https://genshin-impact.fandom.com/api.php"


# ============================================================
# Startup: pre-warm pipeline + DynamoDB caches
# Eliminates 2-5s cold-start from first real user request
# ============================================================
@app.on_event("startup")
async def startup_event():
    """
    Pre-warm pipeline at server startup.
    Inspired by: Claude Code context.ts getSystemContext() / getUserContext()
    — loads all context once at session start, memoizes for reuse.
    """
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _warmup_pipeline)
        logger.info("Pipeline warm-up complete")
    except Exception as e:
        logger.warning("Pipeline warm-up failed (will retry on first request): %s", e)


def _warmup_pipeline():
    pipeline = get_pipeline()
    pipeline.query_processor._load_entity_names()
    pipeline.query_processor._load_alias_map()


# ============================================================
# Pydantic models
# ============================================================

class ThumbnailResponse(BaseModel):
    title: str
    thumbnail_url: Optional[str] = None
    cached: bool = False


class BatchThumbnailRequest(BaseModel):
    titles: list[str]


class BatchThumbnailResponse(BaseModel):
    thumbnails: dict[str, Optional[str]]


class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


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
    session_id: Optional[str] = None
    cache_hit: bool = False


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


# ============================================================
# Helper: normalize pipeline result → QueryResponse fields
# ============================================================

def _build_query_response(result: dict, session_id: Optional[str]) -> QueryResponse:
    sources = []
    for r in result.get("_vector_results", []):
        sources.append(SourceItem(
            title=r.get("title", "Unknown"),
            entity_type=r.get("entity_type", "Lore"),
            section=r.get("section_title"),
            score=r.get("score", 0.0),
            text=r.get("full_text", "")[:500],
            source_url=r.get("source_url"),
            region=r.get("regions", [None])[0] if r.get("regions") else None,
        ))
    if not sources and result.get("sources"):
        for s in result["sources"]:
            sources.append(SourceItem(
                title=s.get("title", "Unknown"),
                entity_type="Lore",
                score=s.get("score", 0.0),
                text="",
            ))

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

    timing_raw = result.get("timing", {})
    timing = TimingData(
        total=timing_raw.get("total", 0.0),
        retrieval=timing_raw.get("retrieval"),
        generation=timing_raw.get("answer_generation"),
    )

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
        session_id=session_id,
        cache_hit=result.get("cache_hit", False),
    )


# ============================================================
# Thumbnail endpoints
# ============================================================

def normalize_title(title: str) -> str:
    return title.replace(" ", "_")


async def fetch_thumbnail_from_fandom(title: str) -> Optional[str]:
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
                if page_id != "-1":
                    thumbnail = page_data.get("thumbnail", {})
                    return thumbnail.get("source")
            return None
        except Exception as e:
            print(f"Error fetching thumbnail for {title}: {e}")
            return None


@app.get("/api/thumbnail/{title}", response_model=ThumbnailResponse)
async def get_thumbnail(title: str):
    if title in thumbnail_cache:
        return ThumbnailResponse(title=title, thumbnail_url=thumbnail_cache[title], cached=True)
    thumbnail_url = await fetch_thumbnail_from_fandom(title)
    thumbnail_cache[title] = thumbnail_url
    return ThumbnailResponse(title=title, thumbnail_url=thumbnail_url, cached=False)


@app.post("/api/thumbnails/batch", response_model=BatchThumbnailResponse)
async def get_thumbnails_batch(request: BatchThumbnailRequest):
    results: dict[str, Optional[str]] = {}
    titles_to_fetch: list[str] = []
    for title in request.titles:
        if title in thumbnail_cache:
            results[title] = thumbnail_cache[title]
        else:
            titles_to_fetch.append(title)
    if titles_to_fetch:
        tasks = [fetch_thumbnail_from_fandom(title) for title in titles_to_fetch]
        fetched = await asyncio.gather(*tasks)
        for title, thumbnail_url in zip(titles_to_fetch, fetched):
            thumbnail_cache[title] = thumbnail_url
            results[title] = thumbnail_url
    return BatchThumbnailResponse(thumbnails=results)


@app.get("/api/health")
async def health_check():
    pipeline = get_pipeline()
    return {
        "status": "healthy",
        "cache_size": len(thumbnail_cache),
        "answer_cache": pipeline.answer_cache.stats(),
    }


_ALLOWED_IMAGE_DOMAINS = frozenset({
    "static.wikia.nocookie.net",
    "vignette.wikia.nocookie.net",
    "genshin-impact.fandom.com",
})


@app.get("/api/image-proxy")
async def proxy_image(url: str):
    from urllib.parse import urlparse
    from fastapi.responses import Response
    parsed = urlparse(url)
    if parsed.hostname not in _ALLOWED_IMAGE_DOMAINS:
        raise HTTPException(status_code=403, detail="Image domain not allowed")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                url, timeout=10.0,
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
                headers={"Cache-Control": "public, max-age=86400"},
            )
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Image not found: {e}")


# ============================================================
# Graph endpoint
# ============================================================

@app.get("/api/graph", response_model=GraphExportResponse)
async def get_full_graph():
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


# ============================================================
# Query endpoint (non-streaming, run_in_executor)
# ============================================================

@app.post("/api/query", response_model=QueryResponse)
async def query_loremaster(request: QueryRequest):
    """
    Non-streaming Q&A endpoint.
    Pipeline runs in thread pool via run_in_executor to avoid blocking the event loop.
    Inspired by: Claude Code LocalAgentTask.tsx — async/sync boundary isolated cleanly.
    """
    try:
        pipeline = get_pipeline()
        loop = asyncio.get_event_loop()

        # Resolve session
        from src.agent.session_manager import get_session_manager
        sm = get_session_manager()
        session = sm.get_or_create(request.session_id)

        # Run blocking pipeline in thread pool
        result = await loop.run_in_executor(
            None, pipeline.answer, request.question, session
        )

        # Update session with this turn (only for non-cache hits)
        if not result.get("cache_hit"):
            # Build sources_payload the same way the streaming endpoint does
            _sources = []
            for r in result.get("_vector_results", []):
                _sources.append({
                    "title": r.get("title", "Unknown"),
                    "entity_type": r.get("entity_type", "Lore"),
                    "section": r.get("section_title"),
                    "score": r.get("score", 0.0),
                    "text": r.get("full_text", "")[:500],
                    "region": r.get("regions", [None])[0] if r.get("regions") else None,
                    "source_url": r.get("source_url", ""),
                })
            sm.add_turn(
                session, request.question, result.get("answer", ""), result.get("entities", []),
                sources=_sources,
                path=result.get("path"),
                graph_results=result.get("graph_results", []),
                query_type=result.get("query_type", "FACTUAL"),
            )

        return _build_query_response(result, session.session_id)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


# ============================================================
# Streaming query endpoint (SSE)
# ============================================================

@app.post("/api/query/stream")
async def query_loremaster_stream(request: QueryRequest):
    """
    Streaming Q&A endpoint using Server-Sent Events.
    TTFB drops from 3-5s to <500ms — tokens arrive as they are generated.

    SSE event types:
    - {"type": "token", "content": "..."}       — incremental answer token
    - {"type": "metadata", "sources": [...], "entities": [...], ...}  — final metadata
    - {"type": "error", "message": "..."}        — error occurred

    Inspired by: Claude Code LocalAgentTask.tsx streaming message queue.
    """
    pipeline = get_pipeline()
    loop = asyncio.get_event_loop()

    from src.agent.session_manager import get_session_manager
    sm = get_session_manager()
    session = sm.get_or_create(request.session_id)

    async def event_stream():
        try:
            # Step 0: Check semantic cache first (fast path, no streaming needed)
            embedding = await loop.run_in_executor(
                None, pipeline.query_processor.embed_query, request.question
            )
            cached = pipeline.answer_cache.lookup(embedding)
            if cached is not None:
                # Return cached answer as a single token burst + metadata
                answer = cached.get("answer", "")
                yield f"data: {json.dumps({'type': 'token', 'content': answer})}\n\n"
                # Reformat raw _vector_results into the same sources_payload shape
                # that the non-cache path sends (text/section keys vs full_text/section_title)
                cached_sources = []
                for r in cached.get("_vector_results", []):
                    cached_sources.append({
                        "title": r.get("title", "Unknown"),
                        "entity_type": r.get("entity_type", "Lore"),
                        "section": r.get("section_title"),
                        "score": r.get("score", 0.0),
                        "text": r.get("full_text", "")[:500],
                        "region": r.get("regions", [None])[0] if r.get("regions") else None,
                        "source_url": r.get("source_url", ""),
                    })
                metadata = {
                    "type": "metadata",
                    "sources": cached_sources,
                    "entities": cached.get("entities", []),
                    "query_type": cached.get("query_type", ""),
                    "path": cached.get("path"),
                    "graph_results": cached.get("graph_results", []),
                    "timing": cached.get("timing", {}),
                    "cost": cached.get("usage", {}).get("cost_usd", 0),
                    "session_id": session.session_id,
                    "cache_hit": True,
                }
                yield f"data: {json.dumps(metadata)}\n\n"
                return

            # Step 1: Query processing (parallel API calls)
            resolved_question = request.question
            if session.turns:
                resolved_question = sm.resolve_coreferences(request.question, session)

            processed = await loop.run_in_executor(
                None, pipeline.query_processor.process, resolved_question
            )

            # Step 2: Retrieval
            retrieval_results = await loop.run_in_executor(
                None,
                lambda: pipeline.retriever.retrieve(
                    query=resolved_question,
                    embedding=processed["embedding"],
                    entities=processed["canonical_entities"],
                    query_type=processed["query_type"],
                    vector_top_k=pipeline.vector_top_k,
                    graph_max_relations=pipeline.graph_max_relations,
                ),
            )

            # Step 3: Context assembly
            context = await loop.run_in_executor(
                None,
                lambda: pipeline.context_assembler.assemble(
                    vector_results=retrieval_results["vector_results"],
                    graph_results=retrieval_results["graph_results"],
                    path_results=retrieval_results.get("path_results"),
                    query_type=processed["query_type"],
                    query_entities=processed["canonical_entities"],
                ),
            )

            # Step 4: Stream answer tokens
            history = sm.get_history_context(session) if session.turns else ""
            full_answer = []

            # generate_stream is a blocking generator — run in thread
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

            def _stream_tokens():
                return list(pipeline.answer_generator.generate_stream(
                    question=request.question,
                    context=context["full_context"],
                    history=history,
                ))

            # We need to yield tokens as they come, not batch them.
            # Use a queue bridge between the sync generator and async generator.
            import queue as _queue
            token_queue: _queue.Queue = _queue.Queue()
            SENTINEL = object()

            def _produce():
                try:
                    for token in pipeline.answer_generator.generate_stream(
                        question=request.question,
                        context=context["full_context"],
                        history=history,
                    ):
                        token_queue.put(token)
                except Exception as exc:
                    token_queue.put(exc)
                finally:
                    token_queue.put(SENTINEL)

            # Start producer in thread
            future = loop.run_in_executor(None, _produce)

            while True:
                # Poll the queue without blocking event loop
                try:
                    item = await loop.run_in_executor(None, token_queue.get)
                except Exception:
                    break
                if item is SENTINEL:
                    break
                if isinstance(item, Exception):
                    yield f"data: {json.dumps({'type': 'error', 'message': str(item)})}\n\n"
                    break
                full_answer.append(item)
                yield f"data: {json.dumps({'type': 'token', 'content': item})}\n\n"

            await future  # ensure thread is done

            # Build path data
            path = None
            path_results = retrieval_results.get("path_results")
            if path_results and path_results.get("found"):
                path = {
                    "nodes": path_results.get("nodes", []),
                    "relations": path_results.get("relations", []),
                    "evidences": path_results.get("evidences", []),
                    "alternative_paths": [
                        {"nodes": alt.get("nodes", []), "relations": alt.get("relations", [])}
                        for alt in path_results.get("alternative_paths", [])
                    ],
                }

            # Serialize graph_results (entity neighborhoods) for fallback constellation
            graph_results_payload = []
            for gr in retrieval_results.get("graph_results", []):
                entity_info = gr.get("entity")
                if not entity_info:
                    continue
                graph_results_payload.append({
                    "entity": {
                        "name": entity_info.get("name", ""),
                        "type": entity_info.get("type", ""),
                        "description": entity_info.get("description", ""),
                    },
                    "relationships": [
                        {
                            "direction": rel.get("direction", "outgoing"),
                            "relation": rel.get("relation", ""),
                            "target": rel.get("target"),
                            "target_type": rel.get("target_type"),
                            "source": rel.get("source"),
                            "source_type": rel.get("source_type"),
                            "evidence": rel.get("evidence"),
                        }
                        for rel in gr.get("relationships", [])[:15]
                    ],
                })

            # Serialize sources for metadata event
            sources_payload = []
            for r in retrieval_results["vector_results"]:
                sources_payload.append({
                    "title": r.get("title", "Unknown"),
                    "entity_type": r.get("entity_type", "Lore"),
                    "section": r.get("section_title"),
                    "score": r.get("score", 0.0),
                    "text": r.get("full_text", "")[:500],
                    "region": r.get("regions", [None])[0] if r.get("regions") else None,
                    "source_url": r.get("source_url", ""),
                })

            final_answer = "".join(full_answer)

            # Update session (store full metadata for history display)
            sm.add_turn(
                session, request.question, final_answer, processed["canonical_entities"],
                sources=sources_payload,
                path=path,
                graph_results=graph_results_payload,
                query_type=processed["query_type"],
            )

            # Store in semantic cache (only for first/single-turn queries)
            if len(session.turns) <= 1:
                pipeline.answer_cache.store(embedding, request.question, {
                    "answer": final_answer,
                    "_vector_results": retrieval_results["vector_results"],
                    "entities": processed["canonical_entities"],
                    "query_type": processed["query_type"],
                    "path": path,
                    "graph_results": graph_results_payload,
                    "timing": {},
                    "usage": {"cost_usd": 0},
                })

            metadata_event = {
                "type": "metadata",
                "sources": sources_payload,
                "entities": processed["canonical_entities"],
                "query_type": processed["query_type"],
                "path": path,
                "graph_results": graph_results_payload,
                "session_id": session.session_id,
                "cache_hit": False,
            }
            yield f"data: {json.dumps(metadata_event)}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ============================================================
# History endpoints
# ============================================================

@app.get("/api/sessions/{session_id}")
async def get_session_history(session_id: str):
    """Return all turns for a session, with full metadata for history display."""
    from src.agent.session_manager import get_session_manager
    sm = get_session_manager()
    session = sm._sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    turns = []
    for i, turn in enumerate(session.turns):
        turns.append({
            "index": i,
            "question": turn.question,
            "answer": turn.answer,
            "entities": turn.entities,
            "timestamp": turn.timestamp,
            "query_type": turn.query_type,
            "sources": turn.sources,
            "path": turn.path,
            "graph_results": turn.graph_results,
        })
    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "last_activity": session.last_activity,
        "turns": turns,
    }


@app.get("/api/cache/history")
async def get_cache_history():
    """Return all cached Q&A entries formatted for the history page."""
    pipeline = get_pipeline()
    entries = []
    for entry in reversed(pipeline.answer_cache._entries):  # newest first
        result = entry.get("result", {})
        # Reformat _vector_results → sources (same logic as cache-hit SSE path)
        sources = []
        for r in result.get("_vector_results", []):
            sources.append({
                "title": r.get("title", "Unknown"),
                "entity_type": r.get("entity_type", "Lore"),
                "section": r.get("section_title"),
                "score": r.get("score", 0.0),
                "text": r.get("full_text", "")[:500],
                "region": r.get("regions", [None])[0] if r.get("regions") else None,
                "source_url": r.get("source_url", ""),
            })
        entries.append({
            "question": entry.get("question", ""),
            "answer": result.get("answer", ""),
            "entities": result.get("entities", []),
            "timestamp": entry.get("ts", 0.0),
            "query_type": result.get("query_type", "FACTUAL"),
            "sources": sources,
            "path": result.get("path"),
            "graph_results": result.get("graph_results", []),
        })
    return {"entries": entries}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
