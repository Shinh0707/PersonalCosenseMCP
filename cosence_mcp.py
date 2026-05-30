import os
import httpx
import urllib.parse
from pathlib import Path
import chromadb
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# --- Load Environment Variables ---
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

PROJECT_NAME = os.getenv("COSENSE_PROJECT_NAME")
EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME")
CONNECT_SID = os.getenv("COSENSE_COOKIE_CONNECT_SID")

BASE_URL = "https://scrapbox.io/api/pages"

# Validate configuration
if not PROJECT_NAME or not EMBEDDING_API_URL or not EMBEDDING_MODEL_NAME:
    raise ValueError("Critical error: COSENSE_PROJECT_NAME or EMBEDDING_API_URL or EMBEDDING_MODEL_NAME is not set in .env file.")

mcp = FastMCP("Personal_Cosense_MCP")

# --- Initialize Vector DB ---
DB_DIR = Path(__file__).parent / "database"
chroma_client = chromadb.PersistentClient(path=str(DB_DIR.resolve()))
collection = chroma_client.get_or_create_collection(name="cosense_pages")

def get_http_headers() -> dict:
    """Helper to generate headers including authentication cookies if available."""
    headers = {}
    if CONNECT_SID:
        headers["Cookie"] = f"connect.sid={CONNECT_SID}"
    return headers

async def get_embedding(text: str) -> list[float]:
    payload = {
        "input": text,
        "model": EMBEDDING_MODEL_NAME
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(EMBEDDING_API_URL, json=payload, timeout=30.0) # type: ignore
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]

async def sync_pages_to_db() -> str:
    """
    Fetches all pages from Cosense using pagination (handling >1000 pages)
    and updates the local vector database with new or updated contents.
    """
    pages = []
    limit = 1000
    skip = 0
    headers = get_http_headers()

    # Loop to handle pagination automatically
    async with httpx.AsyncClient() as client:
        while True:
            url = f"{BASE_URL}/{PROJECT_NAME}?limit={limit}&skip={skip}&sort=updated"
            response = await client.get(url, headers=headers, timeout=30.0)
            
            if response.status_code == 401 or response.status_code == 403:
                return "Error: Unauthorized. Private project requires a valid COSENSE_COOKIE_CONNECT_SID in .env."
            if response.status_code != 200:
                return f"Error: Cosense API returned status code {response.status_code}"
            
            data = response.json()
            fetched_pages = data.get("pages", [])
            if not fetched_pages:
                break
            
            pages.extend(fetched_pages)
            if len(fetched_pages) < limit:
                break  # Reached the end of pages
            
            skip += limit

    if not pages:
        return "No pages found"

    # Get existing items from database to check update timestamps
    existing_data = collection.get(include=["metadatas"])
    existing_metadata_map = {
        meta["id"]: meta for meta in existing_data["metadatas"] if meta is not None and "id" in meta # type: ignore
    }

    docs_to_embed = []
    ids_to_add = []
    metadatas_to_add = []

    for page in pages:
        page_id = page["id"]
        title = page["title"]
        updated = page["updated"]
        descriptions = "\n".join(page.get("descriptions", []))
        embed_text = f"Title: {title}\n{descriptions}"

        # Sync condition: item does not exist or has been modified externally
        if page_id not in existing_metadata_map or existing_metadata_map[page_id]["updated"] < updated:
            docs_to_embed.append(embed_text)
            ids_to_add.append(page_id)
            metadatas_to_add.append({
                "id": page_id,
                "title": title,
                "updated": updated,
                "descriptions": descriptions,
            })

    if not docs_to_embed:
        return "Synced"

    # Progress sequential embeddings
    embeddings_to_add = []
    for text in docs_to_embed:
        try:
            emb = await get_embedding(text)
            embeddings_to_add.append(emb)
        except Exception as e:
            return f"Embedding Error: {str(e)}"

    collection.upsert(
        ids=ids_to_add,
        embeddings=embeddings_to_add,
        metadatas=metadatas_to_add,
        documents=docs_to_embed
    )

    return f"Synced: {len(ids_to_add)} pages added/updated"


@mcp.tool()
async def search_page(query: str, top_k: int = 5) -> str:
    """
    @brief Performs a vector-based semantic search to find conceptually relevant pages.
    @details Best suited for fuzzy, abstract, or conceptual queries like finding old ideas or memories.
    @param query [str] The natural language search query or concept.
    @param top_k [int] Maximum number of results to return (default: 5).
    @return [str] Plain text containing a condensed list of matching pages with pageID, title, and descriptions.
    """
    sync_status = await sync_pages_to_db()
    if "Error" in sync_status:
        return sync_status
    
    try:
        query_embedding = await get_embedding(query)
    except Exception as e:
        return f"Embedding failure: {str(e)}"

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["metadatas"]
    )

    metadatas = results["metadatas"][0] # type: ignore
    if not metadatas:
        return "No matching pages found."

    response_lines = []
    for meta in metadatas:
        response_lines.append(
            f"pageID: {meta['id']}\n"
            f"title: {meta['title']}\n"
            f"snippet: {meta['descriptions'].replace('\n', ' ')}\n" # type: ignore
        )

    return "\n".join(response_lines)


@mcp.tool()
async def search_page_fulltext(query: str) -> str:
    """
    @brief Performs an exact keyword search against the knowledge base using Cosense API.
    @details Best suited for finding specific proper nouns, exact phrases, or technical terms.
    @param query [str] The exact keyword or phrase to match.
    @return [str] Plain text containing a condensed list of matching pages with pageID, title, and descriptions.
    """
    url = f"{BASE_URL}/{PROJECT_NAME}/search/query?q={urllib.parse.quote(query)}"
    headers = get_http_headers()
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 401 or response.status_code == 403:
            return "Error: Unauthorized. Check COSENSE_COOKIE_CONNECT_SID."
        if response.status_code != 200:
            return f"Fulltext search failed: {response.status_code}"
        
        data = response.json()
        pages = data.get("pages", [])
        if not pages:
            return "No matching pages found."
        
        response_lines = []
        for p in pages[:5]:
            page_id = p.get("id", "")
            title = p.get("title", "")
            lines = [line.replace("<b>", "").replace("</b>", "").strip() for line in p.get("lines", [])]
            snippet = " ".join(lines)
            response_lines.append(
                f"pageID: {page_id}\n"
                f"title: {title}\n"
                f"snippet: {snippet}\n"
            )
        
        return "\n".join(response_lines)


@mcp.tool()
async def read_page_details(page_id: str) -> str:
    """
    @brief Retrieves the full content of a specific page using its unique pageID.
    @details Call this tool after identifying a relevant page from search_page or search_page_fulltext.
    @param page_id [str] The unique identification string (pageID) of the target page.
    @return [str] The full markdown/text content of the requested page.
    """
    db_result = collection.get(ids=[page_id], include=["metadatas"])
    if not db_result["metadatas"]:
        return "Error: Specified pageID not found in local index."
    
    raw_title = db_result["metadatas"][0]["title"]
    title = str(raw_title)
    url = f"{BASE_URL}/{PROJECT_NAME}/{urllib.parse.quote(title)}"
    headers = get_http_headers()
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 401 or response.status_code == 403:
            return "Error: Unauthorized. Check COSENSE_COOKIE_CONNECT_SID."
        if response.status_code != 200:
            return f"Failed to retrieve page details: {response.status_code}"
        
        data = response.json()
        lines = [line.get("text", "") for line in data.get("lines", [])]
        relateds_raw= data.get("relatedPages", {}).get("links1hop",[])
        relateds = [f"id:{related_raw.id}, title:{related_raw.title}" for related_raw in relateds_raw]
        return "\n".join(lines) + "\n\nRelateds:[\n" + ",\n".join(relateds) + "\n]"

if __name__ == "__main__":
    mcp.run(transport="stdio")