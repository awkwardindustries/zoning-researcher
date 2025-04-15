import logging
import os
from pathlib import Path

import anyio
import click
import mcp.types as types
import requests
from browser_use_runner import run_browser_use
from mcp.server.lowlevel import Server

server = Server("browser-server")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mcp-server:browser:browser_server")
logger.setLevel(logging.DEBUG)

local_download_path = os.getenv('DOWNLOAD_FULL_PATH', './tmp/downloads/')

#region List Tools

@server.list_tools()
async def list_tools() -> list[types.Tool]:
	"""
	Lists tools available on this server
	"""
	return [
		types.Tool(
			name="download_regulations",
			description="""
Browses to the zoning website for the specified location and downloads them to a 
local file or files.
			""",
			inputSchema={
				"type": "object",
				"required": ["location"],
				"properties": {
					"location": {
						"type": "string",
						"description": "Location for which to find its regulations",
					}
				},
			},
		),
		types.Tool(
			name="download_file_from_url",
			description="Downloads the file from the given URL.",
			inputSchema={
				"type": "object",
				"required": ["url"],
				"properties": {
					"url": {
						"type": "string",
						"description": "URL to the file",
					}
				},
			},
		),
		types.Tool(
			name="browse_for_regulation_information",
			description="""
Browses to the zoning website for the specified location and finds information to 
answer the provided question.
			""",
			inputSchema={
				"type": "object",
				"required": ["location", "question"],
				"properties": {
					"location": {
						"type": "string",
						"description": "Location for which to find its regulations",
					},
					"question": {
						"type": "string",
						"description": "Question we're trying to answer"
					}
				},
			},
		),
	]

#endregion

#region Setup tool handlers

class ToolHandler:
	"""
	Base class defining the handle method required for all tools
	"""
	async def handle(
		self, name: str, arguments: dict | None
	) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
		raise NotImplementedError
	
class BrowseForRegulationInformationToolHandler(ToolHandler):
	"""
	Tool that uses browser_use to find information on the web that can be used
	by an LLM for context to answer questions. It's a fallback if files cannot
	be downloaded.
	"""
	async def handle(
		self, name: str, arguments: dict | None
	) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
		location = arguments["location"]
		question = arguments["question"]
		output = None

		try:
			prompt = f"""
Find the website that provides zoning laws and/or regulations for {location}. Try to
find content or context to answer the question provided: {question}. If you find
content that can answer the question, provide that in the final result. If you cannot,
state clearly that you cannot find information to answer the question.
"""
			response = await run_browser_use(prompt)
			logger.info(f'browser_use reponse received: {response}')
			output = response["output_text"]
		except Exception as exception:
			logger.exception(exception)
			output = exception

		return [types.TextContent(type="text", text=output)]

class DownloadRegulationsToolHandler(ToolHandler):
	"""
	Tool that uses browser_use to find zoning regulations and downloads them to
	a local file. Note that downloading from a PDF Viewer is a known bug, so not
	all PDFs are downloadable. The browse_for_regulation_information tool might
	be used as a backup to read/find the information to answer the question
	without requiring it be part of a downloaded/ingested knowledge base.
	"""
	async def handle(
		self, name: str, arguments: dict | None
	) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
		location = arguments["location"]
		output = None

		try:
			prompt = f"""
Find the website that provides zoning laws and/or regulations for {location} and 
download them to a local file. If you end up with the file in a PDF viewer,
stop trying to download. Respond with the URL to the PDF file and say that
you were unable to download it locally.
"""
			response = await run_browser_use(prompt)
			logger.info(f'browser_use reponse received: {response}')
			output = response["output_text"]
		except Exception as exception:
			logger.exception(exception)
			output = exception

		return [types.TextContent(type="text", text=output)]

class DownloadFileFromUrlToolHandler(ToolHandler):
	"""
	Tool that is only responsible for downloading a file given a URL.
	"""
	async def handle(
		self, name: str, arguments: dict | None
	) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
		url = arguments["url"]
		output = None

		try:
			response = requests.get(url)
			fragment_removed = url.split("#")[0]
			query_string_removed = fragment_removed.split("?")[0]
			scheme_removed = query_string_removed.split("://")[-1].split(":")[-1]
			if scheme_removed.find("/") == -1:
				output = f"The URL ({url}) could not be parsed to find a filename."
			else:
				file_name = os.path.basename(scheme_removed)
				full_path = Path(local_download_path, file_name)
				with open(full_path, 'wb') as f:
					f.write(response.content)
				output = f"File successfully downloaded: {full_path}"
		except Exception as exception:
			logger.exception(exception)
			output = exception
		
		return [types.TextContent(type="text", text=output)]

#endregion

#region Setup tool invocation

tool_handlers = {
	"download_regulations": DownloadRegulationsToolHandler(),
	"download_file_from_url": DownloadFileFromUrlToolHandler(),
	"browse_for_regulation_information": BrowseForRegulationInformationToolHandler(),
}

@server.call_tool()
async def handle_call_tool(
	name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
	"""
	Handle requests to execute the server tool.
	"""
	if name in tool_handlers:
		return await tool_handlers[name].handle(name, arguments)
	else:
		raise ValueError(f"Unknown tool: {name}")

#endregion

#region Main

@click.command()
@click.option("--port", default=8000, help="Port to listen on for SSE")
@click.option(
	"--transport", 
	type=click.Choice(["stdio", "sse"]), 
	default="stdio", 
	help="Transport type",
)
def main(port: int, transport: str) -> int:
	if transport == "sse":
		from mcp.server.sse import SseServerTransport
		from starlette.applications import Starlette
		from starlette.routing import Mount, Route

		sse = SseServerTransport("/messages/")

		async def handle_sse(request):
			async with sse.connect_sse(
				request.scope, request.receive, request._send
			) as streams:
				await server.run(
					streams[0], streams[1], server.create_initialization_options()
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
				await server.run(
					streams[0], streams[1], server.create_initialization_options()
				)

		anyio.run(arun)

	return 0

#endregion