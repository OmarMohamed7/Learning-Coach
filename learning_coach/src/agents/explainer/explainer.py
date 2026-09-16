
from dotenv import load_dotenv
from mcp_client.client import get_mcp_tools

load_dotenv()

tools = {}
async def get_mcps_tools() :
    tools = await get_mcp_tools()
    print(f"Discovered {len(tools)} tools:")
    
    tools = {t.name: t for t in tools}
    
    print(tools)
    
        
if __name__ == '__main__':
    import asyncio
    asyncio.run(get_mcps_tools())