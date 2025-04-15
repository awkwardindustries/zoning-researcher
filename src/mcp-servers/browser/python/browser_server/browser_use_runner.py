import os

from browser_use.agent.service import Agent
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import BrowserContext, BrowserContextConfig
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from pydantic import SecretStr

load_dotenv('../../../../../.env', override=False)

local_download_path = os.getenv('DOWNLOAD_FULL_PATH', './tmp/downloads/')

required_env_vars = ['AZURE_OPENAI_KEY', 'AZURE_OPENAI_ENDPOINT']
for var in required_env_vars:
	if not os.getenv(var):
		raise ValueError(f'{var} is not set. Please add it to your .env file.')
      
async def run_browser_use(prompt: str) -> dict[str, any]:
	"""
	Function to create and execute a browser_use agent with a variable prompt.
	It may be re-run multiple time, and each time should start from the same
	clean slate without memory or knowledge of previous runs.
	"""
	try:
		config = BrowserContextConfig(save_downloads_path=local_download_path)
		
		browser = Browser(
			BrowserConfig(
				headless=False,  # True when not debugging
				disable_security=True,
				new_context_config=BrowserContextConfig(
					disable_security=True,
					minimum_wait_page_load_time=1, # 3 on prod
					maximum_wait_page_load_time=10, # 20 on prod
					browser_window_size={
						'width': 1280,
						'height': 1100,
					},
				)
			)
		)

		context = BrowserContext(browser=browser, config=config)

		llm = AzureChatOpenAI(
			model=os.getenv('AZURE_OPENAI_MODEL_NAME', 'gpt-4o'),
			api_version=os.getenv('AZURE_OPENAI_MODEL_API_VERSION', '2024-10-21'),
			azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
			api_key=SecretStr(os.getenv('AZURE_OPENAI_KEY', '')),
		)

		agent = Agent(
			task=prompt,
			llm=llm,
			browser_context=context,
			validate_output=True,
		)
		result = await agent.run(max_steps=50)
		
		response = None
		if result.is_done():
			# Get the last action summary
			final_result = result.final_result()
			response = {
				'output_text': str(final_result),
			}
		
		if result is None:
			raise Exception(f'Something went wrong following these directions: {prompt}')

		return response

	finally:
		# Try to cleanup. This isn't great as documented by browser_use folks.
		#session = await browser.playwright_browser.new_browser_cdp_session()
		#await session.send("Browser.close")
		await context.close()
		await browser.close()
