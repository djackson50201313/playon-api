import re
import json
import mechanize
import xml.etree.ElementTree as ET
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from datetime import datetime

app = FastAPI(title="Media Provider API with MCP Server",
              description="API for searching and retrieving media from providers with MCP support")


# MCP Protocol Models
class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


class ToolInfo(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any]


# MCP Tools Definition
MCP_TOOLS = [
    ToolInfo(
        name="search_media",
        description="Search for media (movies or TV shows) across multiple providers",
        inputSchema={
            "type": "object",
            "properties": {
                "search_term": {
                    "type": "string",
                    "description": "The media title to search for"
                },
                "media_type": {
                    "type": "string",
                    "enum": ["show", "movie"],
                    "description": "Type of media to search for",
                    "default": "show"
                },
                "match_type": {
                    "type": "string",
                    "enum": ["partial", "exact"],
                    "description": "How to match the search term",
                    "default": "partial"
                },
                "excluded_providers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of provider names to exclude from search",
                    "default": []
                },
                "server": {
                    "type": "string",
                    "description": "Media server IP address",
                    "default": "192.168.2.14"
                }
            },
            "required": ["search_term"]
        }
    ),
    ToolInfo(
        name="list_providers",
        description="Get a list of all available media providers",
        inputSchema={
            "type": "object",
            "properties": {
                "server": {
                    "type": "string",
                    "description": "Media server IP address",
                    "default": "192.168.2.14"
                }
            },
            "required": []
        }
    ),
    ToolInfo(
        name="trace_media_folder",
        description="Explore the contents of a media folder to find video files",
        inputSchema={
            "type": "object",
            "properties": {
                "href": {
                    "type": "string",
                    "description": "The href path of the folder to explore"
                },
                "name": {
                    "type": "string",
                    "description": "The name of the folder"
                },
                "provider": {
                    "type": "string",
                    "description": "The provider name"
                },
                "type": {
                    "type": "string",
                    "description": "The type of the item (should be 'folder')"
                },
                "server": {
                    "type": "string",
                    "description": "Media server IP address",
                    "default": "192.168.2.14"
                }
            },
            "required": ["href", "name", "provider", "type"]
        }
    )
]


# Original functions (unchanged)
def get_providers(server: str = "192.168.2.14") -> Dict[str, Dict[str, str]]:
    br = mechanize.Browser()
    br.set_handle_robots(False)
    response = br.open(f"http://{server}:54479/data/data.xml")
    page_source = response.read()
    root = ET.fromstring(page_source)

    providers = {}
    for group in root.findall('group'):
        if group.get('id'):
            providers[group.get('name')] = {
                'href': group.get('href'),
                'id': group.get('id')
            }
    return providers


def query_provider(provider: str, search_term: str, server: str = "192.168.2.14") -> List[Dict[str, str]]:
    br = mechanize.Browser()
    br.set_handle_robots(False)
    url = f"http://{server}:54479/data/data.xml?id={provider}&searchterm={search_term}"
    results = []

    try:
        response = br.open(url)
        page_source = response.read()
        root = ET.fromstring(page_source)

        for ea_result in root.findall('group'):
            if 'id' not in ea_result.attrib:
                results.append({
                    'href': ea_result.get('href'),
                    'name': ea_result.get('name'),
                    'provider': provider,
                    'type': ea_result.get('type')
                })
    except Exception as e:
        print(f"Error querying provider: {e}")

    return results


def trace_folder(result: Dict[str, str], server: str = "192.168.2.14") -> List[Dict[str, str]]:
    br = mechanize.Browser()
    br.set_handle_robots(False)
    url = f"http://{server}:54479{result['href']}"
    search_results = []

    try:
        response = br.open(url)
        page_source = response.read()
        root = ET.fromstring(page_source)

        for ea_result in root.findall('group'):
            if ea_result.get('href') == result['href']:
                continue

            if ea_result.get('childs', None) is not None:
                search_results.extend(trace_folder(ea_result, server))

            if ea_result.get('type') == 'video':
                search_results.append(ea_result)
    except Exception as e:
        print(f"Error tracing folder: {e}")

    return search_results


def single_match(result: Dict[str, str], pattern: re.Pattern, media_type: str, server: str = "192.168.2.14") -> bool:
    if pattern.match(result['name']):
        if result['type'] == 'folder':
            results = trace_folder(result=result, server=server)
            if len(results) > 2 and media_type == 'show':
                return True
            elif media_type == 'movie':
                return True
            else:
                return False
        elif result['type'] == 'video':
            if media_type == 'show':
                return False
            else:
                return True
        else:
            print(f"What kind of type is this??? {result['type']}")
            return False
    else:
        return False


def filter_results(results: List[Dict[str, str]], search_term: str, media_type: str, match_type: str = 'partial') -> \
List[Dict[str, str]]:
    pattern = re.compile(".*" + search_term, re.IGNORECASE)
    if match_type == 'exact':
        pattern = re.compile(f"^{search_term}$", re.IGNORECASE)

    filtered_results = [
        result for result in results
        if single_match(result, pattern, media_type)
    ]

    return filtered_results


# MCP Protocol Handlers
async def handle_initialize(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP initialize request"""
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {
                "listChanged": False
            }
        },
        "serverInfo": {
            "name": "media-provider-server",
            "version": "1.0.0"
        }
    }


async def handle_tools_list(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP tools/list request"""
    return {
        "tools": [tool.dict() for tool in MCP_TOOLS]
    }


async def handle_tools_call(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP tools/call request"""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    try:
        if tool_name == "search_media":
            search_term = arguments.get("search_term")
            media_type = arguments.get("media_type", "show")
            match_type = arguments.get("match_type", "partial")
            excluded_providers = arguments.get("excluded_providers", [])
            server = arguments.get("server", "192.168.2.14")

            if media_type not in ['show', 'movie']:
                raise ValueError("Media type must be 'show' or 'movie'")

            providers = get_providers(server)
            filtered_results = []

            for provider_name, provider_info in providers.items():
                if provider_name in excluded_providers:
                    continue

                url_search_term = '%20'.join(search_term.split())
                results = query_provider(provider_info['id'], url_search_term, server)
                filtered_results.extend(
                    filter_results(results, search_term, media_type, match_type)
                )

            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Found {len(filtered_results)} results for '{search_term}':\n\n" +
                                "\n".join([f"• {r['name']} ({r['type']}) - {r['provider']}" for r in filtered_results])
                    }
                ],
                "isError": False
            }

        elif tool_name == "list_providers":
            server = arguments.get("server", "192.168.2.14")
            providers = get_providers(server)

            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Available providers ({len(providers)}):\n\n" +
                                "\n".join([f"• {name}: {info['id']}" for name, info in providers.items()])
                    }
                ],
                "isError": False
            }

        elif tool_name == "trace_media_folder":
            result = {
                "href": arguments.get("href"),
                "name": arguments.get("name"),
                "provider": arguments.get("provider"),
                "type": arguments.get("type")
            }
            server = arguments.get("server", "192.168.2.14")

            folder_contents = trace_folder(result, server)

            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Contents of folder '{result['name']}':\n\n" +
                                "\n".join([f"• {item.get('name', 'Unknown')} ({item.get('type', 'unknown')})"
                                           for item in folder_contents])
                    }
                ],
                "isError": False
            }

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error executing tool '{tool_name}': {str(e)}"
                }
            ],
            "isError": True
        }


# MCP Endpoints
@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """Main MCP protocol endpoint"""
    try:
        body = await request.body()
        data = json.loads(body)

        mcp_request = MCPRequest(**data)

        result = None
        error = None

        try:
            if mcp_request.method == "initialize":
                result = await handle_initialize(mcp_request.params or {})
            elif mcp_request.method == "tools/list":
                result = await handle_tools_list(mcp_request.params or {})
            elif mcp_request.method == "tools/call":
                result = await handle_tools_call(mcp_request.params or {})
            else:
                error = {
                    "code": -32601,
                    "message": f"Method not found: {mcp_request.method}"
                }
        except Exception as e:
            error = {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }

        response = MCPResponse(
            id=mcp_request.id,
            result=result,
            error=error
        )

        return JSONResponse(response.dict(exclude_none=True))

    except Exception as e:
        error_response = MCPResponse(
            error={
                "code": -32700,
                "message": f"Parse error: {str(e)}"
            }
        )
        return JSONResponse(error_response.dict(exclude_none=True))


# Original FastAPI endpoints (unchanged)
@app.get("/providers", response_model=Dict[str, Dict[str, str]])
def list_providers_endpoint(server: str = "192.168.2.14"):
    """
    Get list of available media providers
    """
    return get_providers(server)


@app.get("/search", response_model=List[Dict[str, str]])
def search_media_endpoint(
        search_term: str = Query(..., description="Search term for media"),
        media_type: str = Query('show', description="Type of media (show or movie)"),
        match_type: str = Query('partial', description="Matching type (partial or exact)"),
        excluded_providers: Optional[List[str]] = Query(None, description="Providers to exclude"),
        server: str = "192.168.2.14"
):
    """
    Search for media across providers
    """
    if media_type not in ['show', 'movie']:
        raise HTTPException(status_code=400, detail="Media type must be 'show' or 'movie'")

    providers = get_providers(server)
    filtered_results = []

    for provider_name, provider_info in providers.items():
        if excluded_providers and provider_name in excluded_providers:
            continue

        url_search_term = '%20'.join(search_term.split())
        results = query_provider(provider_info['id'], url_search_term, server)
        filtered_results.extend(
            filter_results(results, search_term, media_type, match_type)
        )

    return filtered_results


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
