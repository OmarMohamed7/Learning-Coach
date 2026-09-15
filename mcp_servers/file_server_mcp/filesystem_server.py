
import os
from pathlib import Path

from audit_query import query_audit
from mcp.server.fastmcp import FastMCP

from logger import get_logger

logger = get_logger(__name__)

mcp = FastMCP(
    "Filesystem Server",
    host=os.getenv("MCP_HTTP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_HTTP_PORT", "8001")),
)

NOTES_BASE = Path(os.getenv("NOTES_PATH","study_materials/sample_notes"))

@mcp.tool()
def list_study_files() -> list[str]:

    """
    List all available study notes files.

    Return a list of filenames relative to the notes directory.
    Examples: ['closures.md', 'decorators.md']

    Always call this first to discover what materials are available before attempting
    to read specefic files
    """

    if not NOTES_BASE.exists():
        logger.warning("Notes directory not found: %s", NOTES_BASE)
        return []

    return sorted(
        [
            str(f.relative_to(NOTES_BASE))
            for f in NOTES_BASE.rglob("*.md")
        ]
    )
    
        
@mcp.tool()
def read_study_file(filename: str) -> str:
    """
    Read the full content of a study note file
    
    Args:
        filename: the filename to read, exactly as 
        returned from list_study_files()
        
    Returns the full rext content, or an error string not found 
    """
    
    file_path = NOTES_BASE / filename
    
    try:
        resolved = file_path.resolve()
        """
        relative to used as a security check to check whether the resolved inside the notebase path or not 
        if not this will raise ValueError
        """
        resolved.relative_to(NOTES_BASE.resolve())
        
    except ValueError:
        return (
            f"Access outside the study materials directory is forbidden"
        )
        
    if not file_path.exists():
        logger.error(f"Error: {filename} not found inside this directory {file_path}")
        return f"Error: {filename} not found"
    
    if file_path.suffix != '.md':
        logger.error(f"Error: {filename} not supported, Only md files are supported")
        return f"Error: Only md files are supported"
    
    try:
        return file_path.read_text(encoding="utf-8")
    except (PermissionError, OSError) as e:
        logger.error(f"Error Reading {filename}: {e}")
        return f"Error: reading {filename}"

@mcp.tool()
def search_notes(query: str) -> list[dict]:
    """
    Search across all study notes for a keyword or phrase
    
    Args:
        query: the search term
        
    Returns aa list of matches, each with keys : 'file' 'line_number' 'line'
    Maximum 20 results to avoid overwhelming the context window.
    
    Later we can add pagination. and solve the problem not searching again from start
    """
    
    if not NOTES_BASE.exists():
        return []
    
    results = []
    query = query_audit(query)
    
    for file_path in sorted(NOTES_BASE.rglob("*.md")):
        rel_path = str(file_path.relative_to(NOTES_BASE))
        
        try:
            lines = file_path.read_text(encoding='UTF-8').splitlines()
        except (UnicodeDecodeError, PermissionError, OSError) as e:
            logger.error(f"Can not read file {file_path} : {e}")
            continue
        
        for line_num, line in enumerate(lines, 1):
            if query in line.lower():
                results.append(
                    {
                        "file": rel_path,
                        "line_numeber": line_num,
                        "line": line
                    }
                )
                
                if len(results) >= 20:
                    return results
    
    return results

@mcp.resource("notes://index")
# MCP Resource provide a read-only data to llm to provide him with logger file or any file
# in read-only mode
# unlike tool give the agent ability to do some task
def get_notes_index() -> str:
    """
    Resource: index of all available study materials with file sizes.
    URI: notes://index
    """
    
    files = list_study_files()
    if not files:
        return "# Study Materials Index\n\nNo study materials found."
    
    lines = ["# Study Materials Index\n"]
    
    for filename in files:
        file_path: Path = NOTES_BASE / filename
        try:
            size_kb = file_path.stat().st_size / 1024
            lines.append(f"- **{filename}** ({size_kb:.1f} KB)")
        except OSError:
            lines.append(f"- **{filename}** (size unknown)")
        
    lines.append(f"\nTotal: {len(files)} file(s)")
    return "\n".join(lines)

if __name__ == '__main__':
    logger.info(f"[Filesystem MCP] Serving files from: {NOTES_BASE.resolve()}")
    mcp.run(transport="streamable-http")