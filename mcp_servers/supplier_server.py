"""
MCP server simulating a supplier API.
Uses a plain ASGI callable to avoid Starlette's response-wrapper issues with
the MCP SSE transport (which writes directly to the ASGI send callable and
returns None instead of a Response object).
"""
import hashlib
import json
import os
import uuid
from datetime import date, timedelta

import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool

server = Server("supplier-mcp-server")
sse = SseServerTransport("/messages/")

SUPPLIERS = [
    {"name": "FreshFarm Co.",          "reliability": 0.94, "contact": "orders@freshfarm.com"},
    {"name": "QuickStock Ltd.",         "reliability": 0.88, "contact": "supply@quickstock.com"},
    {"name": "Prime Distributors Inc.", "reliability": 0.96, "contact": "b2b@primedist.com"},
    {"name": "NationWide Goods",        "reliability": 0.79, "contact": "wholesale@nwgoods.com"},
    {"name": "Metro Wholesale",         "reliability": 0.91, "contact": "orders@metrowholesale.com"},
]

CATEGORY_LEAD_TIMES: dict[str, int] = {
    "dairy": 2, "beverages": 3, "snacks": 4, "produce": 1,
    "frozen": 3, "bakery": 1, "meat": 2, "household": 5,
    "personal_care": 6, "grains": 5, "condiments": 5,
}


def _supplier(supplier_id: str) -> dict:
    idx = int(hashlib.md5(supplier_id.encode()).hexdigest(), 16) % len(SUPPLIERS)
    return SUPPLIERS[idx]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_supplier_info",
            description="Get supplier name, reliability score, and contact info.",
            inputSchema={
                "type": "object",
                "properties": {"supplier_id": {"type": "string"}},
                "required": ["supplier_id"],
            },
        ),
        Tool(
            name="get_lead_time",
            description="Get estimated lead time in days for a product category from this supplier.",
            inputSchema={
                "type": "object",
                "properties": {
                    "supplier_id": {"type": "string"},
                    "product_category": {"type": "string"},
                },
                "required": ["supplier_id", "product_category"],
            },
        ),
        Tool(
            name="create_purchase_order",
            description="Create a purchase order with the supplier. Returns order_id and estimated delivery date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "supplier_id": {"type": "string"},
                    "product_id": {"type": "string"},
                    "product_name": {"type": "string"},
                    "quantity": {"type": "integer"},
                    "priority": {"type": "string"},
                },
                "required": ["supplier_id", "product_id", "product_name", "quantity", "priority"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    args = arguments or {}

    if name == "get_supplier_info":
        s = _supplier(args["supplier_id"])
        result = {
            "supplier_id": args["supplier_id"],
            "name": s["name"],
            "reliability_score": s["reliability"],
            "contact_email": s["contact"],
            "active": True,
        }

    elif name == "get_lead_time":
        s = _supplier(args["supplier_id"])
        base = CATEGORY_LEAD_TIMES.get(args["product_category"].lower(), 5)
        if s["reliability"] >= 0.90:
            adjusted, variability = base, "low"
        elif s["reliability"] >= 0.80:
            adjusted, variability = base + 1, "medium"
        else:
            adjusted, variability = base + 2, "high"
        result = {
            "supplier_id": args["supplier_id"],
            "supplier_name": s["name"],
            "product_category": args["product_category"],
            "lead_time_days": adjusted,
            "variability": variability,
        }

    elif name == "create_purchase_order":
        s = _supplier(args["supplier_id"])
        offset = {"critical": -1, "high": 0}.get(args["priority"], 1)
        lead_days = max(1, 3 + offset)
        estimated_delivery = date.today() + timedelta(days=lead_days)
        order_id = f"PO-{uuid.uuid4().hex[:8].upper()}"
        result = {
            "order_id": order_id,
            "status": "submitted",
            "supplier_name": s["name"],
            "product_id": args["product_id"],
            "product_name": args["product_name"],
            "quantity_ordered": args["quantity"],
            "priority": args["priority"],
            "estimated_delivery_date": str(estimated_delivery),
            "contact_email": s["contact"],
        }

    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result))]


# ── Plain ASGI app — no Starlette Route wrapper so MCP transport owns the response ──

async def app(scope, receive, send):
    if scope["type"] != "http":
        return

    path = scope.get("path", "")

    if path == "/health":
        body = json.dumps({"status": "ok", "server": "supplier-mcp"}).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [[b"content-type", b"application/json"]]})
        await send({"type": "http.response.body", "body": body})

    elif path == "/sse":
        async with sse.connect_sse(scope, receive, send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    elif path.startswith("/messages"):
        await sse.handle_post_message(scope, receive, send)

    else:
        body = json.dumps({"error": "not found"}).encode()
        await send({"type": "http.response.start", "status": 404,
                    "headers": [[b"content-type", b"application/json"]]})
        await send({"type": "http.response.body", "body": body})


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8002"))
    uvicorn.run("mcp_servers.supplier_server:app", host="0.0.0.0", port=port, log_level="info")
