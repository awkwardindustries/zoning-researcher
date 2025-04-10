import anyio
import click
import mcp.types as types
from mcp.server.lowlevel import Server

async def lookup_regulations(
    location: str,
) -> list[types.TextContent]:
	return [types.TextContent(type="text", text="response from browser-use")]

@click.command()
@click.option("--port", default=8000, help="Port to listen on for SSE")
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio", help="Transport type")
def main(port: int, transport: str) -> int:
	app = Server("mcp-zoning-regulations-fetcher")

	@app.call_tool()
	async def fetch_tool(
		name: str, arguments: dict
	) -> list[types.TextContent]:
		if name != "fetch":
			raise ValueError(f"Unknown tool: {name}")
		if "location" not in arguments:
			raise ValueError("Missing required argument 'location'")
		return await lookup_regulations(arguments["location"])

	@app.list_tools()
	async def list_tools() -> list[types.Tool]:
		return [
            types.Tool(
                name="fetch",
                description="Browses to find the website for the specified location that provides and downloads the zoning regulations",
                inputSchema={
                    "type": "object",
                    "required": ["location"],
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The location for which to find its zoning regulations",
						}
					},
				},
			)
		]

	if transport == "sse":
		from mcp.server.sse import SseServerTransport
		from starlette.applications import Starlette
		from starlette.routing import Mount, Route

		sse = SseServerTransport("/messages/")

		async def handle_sse(request):
			async with sse.connect_sse(
				request.scope, request.receive, request._send
			) as streams:
				await app.run(
					streams[0], streams[1], app.create_initialization_options()
				)

		starlette_app = Starlette(
			debug=True,
			routes=[
				Route("/sse", endpoint=handle_sse),
				Mount("/messages/", app=sse.handle_post_message),
			],
		)

		import uvicorn

		uvicorn.run(starlette_app, host="0.0.0.0", port=port)
	else:
		from mcp.server.stdio import stdio_server

		async def arun():
			async with stdio_server() as streams:
				await app.run(
					streams[0], streams[1], app.create_initialization_options()
				)

		anyio.run(arun)

	return 0