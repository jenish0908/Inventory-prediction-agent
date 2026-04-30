"""
MCP server wrapping the inventory PostgreSQL database.
Uses a plain ASGI callable to avoid Starlette's response-wrapper issues with
the MCP SSE transport (which writes directly to the ASGI send callable and
returns None instead of a Response object).
"""
import json
import os
from datetime import date, timedelta

import asyncpg
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/inventory_db",
).replace("postgresql+asyncpg://", "postgresql://")

server = Server("inventory-mcp-server")
sse = SseServerTransport("/messages/")

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_product_info",
            description="Fetch product metadata: name, category, supplier_id, lead_time_days, reorder_point, current_stock.",
            inputSchema={
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        ),
        Tool(
            name="get_stock_level",
            description="Get current stock level and reorder point for a product.",
            inputSchema={
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        ),
        Tool(
            name="get_sales_history",
            description="Get sales history for the last N days (default 30).",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "days": {"type": "integer", "default": 30},
                },
                "required": ["product_id"],
            },
        ),
        Tool(
            name="log_restock_recommendation",
            description="Log an autonomous restock recommendation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "recommended_quantity": {"type": "integer"},
                    "priority": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["product_id", "recommended_quantity", "priority", "reason"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    args = arguments or {}

    if name == "get_product_info":
        pool = await _get_pool()
        row = await pool.fetchrow(
            "SELECT id, name, category, supplier_id, lead_time_days, reorder_point, current_stock "
            "FROM products WHERE id = $1::uuid",
            args["product_id"],
        )
        result = (
            {"error": f"Product {args['product_id']} not found"}
            if row is None
            else {
                "id": str(row["id"]),
                "name": row["name"],
                "category": row["category"],
                "supplier_id": str(row["supplier_id"]),
                "lead_time_days": row["lead_time_days"],
                "reorder_point": row["reorder_point"],
                "current_stock": row["current_stock"],
            }
        )

    elif name == "get_stock_level":
        pool = await _get_pool()
        row = await pool.fetchrow(
            "SELECT current_stock, reorder_point FROM products WHERE id = $1::uuid",
            args["product_id"],
        )
        result = (
            {"error": f"Product {args['product_id']} not found"}
            if row is None
            else {
                "current_stock": row["current_stock"],
                "reorder_point": row["reorder_point"],
                "below_reorder_point": row["current_stock"] <= row["reorder_point"],
            }
        )

    elif name == "get_sales_history":
        pool = await _get_pool()
        days = int(args.get("days", 30))
        cutoff = date.today() - timedelta(days=days)
        rows = await pool.fetch(
            "SELECT sale_date, units_sold FROM sales_history "
            "WHERE product_id = $1::uuid AND sale_date >= $2 ORDER BY sale_date DESC",
            args["product_id"],
            cutoff,
        )
        history = [{"sale_date": str(r["sale_date"]), "units_sold": r["units_sold"]} for r in rows]
        avg_daily = sum(r["units_sold"] for r in rows) / len(rows) if rows else 0.0
        result = {
            "product_id": args["product_id"],
            "days_requested": days,
            "records_found": len(history),
            "history": history,
            "avg_daily_sales": round(avg_daily, 2),
        }

    elif name == "log_restock_recommendation":
        result = {
            "status": "logged",
            "product_id": args["product_id"],
            "recommended_quantity": args["recommended_quantity"],
            "priority": args["priority"],
            "message": (
                f"Restock recommendation recorded: {args['recommended_quantity']} units "
                f"at {args['priority']} priority."
            ),
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
        body = json.dumps({"status": "ok", "server": "inventory-mcp"}).encode()
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
    port = int(os.getenv("MCP_PORT", "8001"))
    uvicorn.run("mcp_servers.inventory_server:app", host="0.0.0.0", port=port, log_level="info")
