"""
Typed async clients for the inventory and supplier MCP servers.
Each method opens an SSE connection, calls one tool, and returns parsed JSON.
"""
import json

from mcp import ClientSession
from mcp.client.sse import sse_client

from app.config import settings


async def _call_tool(server_url: str, tool_name: str, arguments: dict) -> dict:
    try:
        async with sse_client(f"{server_url}/sse") as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return json.loads(result.content[0].text)
    except* Exception as eg:
        # Unwrap ExceptionGroup from anyio TaskGroup and re-raise with context
        causes = [str(e) for e in eg.exceptions]
        raise RuntimeError(
            f"MCP call failed [{server_url} → {tool_name}]: {'; '.join(causes)}"
        ) from eg.exceptions[0]


class InventoryMCPClient:
    def __init__(self, base_url: str) -> None:
        self._url = base_url

    async def get_product_info(self, product_id: str) -> dict:
        return await _call_tool(self._url, "get_product_info", {"product_id": product_id})

    async def get_stock_level(self, product_id: str) -> dict:
        return await _call_tool(self._url, "get_stock_level", {"product_id": product_id})

    async def get_sales_history(self, product_id: str, days: int = 30) -> dict:
        return await _call_tool(
            self._url, "get_sales_history", {"product_id": product_id, "days": days}
        )

    async def log_restock_recommendation(
        self, product_id: str, quantity: int, priority: str, reason: str
    ) -> dict:
        return await _call_tool(
            self._url,
            "log_restock_recommendation",
            {
                "product_id": product_id,
                "recommended_quantity": quantity,
                "priority": priority,
                "reason": reason,
            },
        )


class SupplierMCPClient:
    def __init__(self, base_url: str) -> None:
        self._url = base_url

    async def get_supplier_info(self, supplier_id: str) -> dict:
        return await _call_tool(self._url, "get_supplier_info", {"supplier_id": supplier_id})

    async def get_lead_time(self, supplier_id: str, product_category: str) -> dict:
        return await _call_tool(
            self._url,
            "get_lead_time",
            {"supplier_id": supplier_id, "product_category": product_category},
        )

    async def create_purchase_order(
        self,
        supplier_id: str,
        product_id: str,
        product_name: str,
        quantity: int,
        priority: str,
    ) -> dict:
        return await _call_tool(
            self._url,
            "create_purchase_order",
            {
                "supplier_id": supplier_id,
                "product_id": product_id,
                "product_name": product_name,
                "quantity": quantity,
                "priority": priority,
            },
        )


inventory_mcp = InventoryMCPClient(settings.inventory_mcp_url)
supplier_mcp = SupplierMCPClient(settings.supplier_mcp_url)
