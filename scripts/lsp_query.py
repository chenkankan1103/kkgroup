#!/usr/bin/env python3
"""
LSP (Pylance) Query Tool
Query the Python Language Server for precise code intelligence.

Usage:
    python scripts/lsp_query.py refs update_user_kkcoin
    python scripts/lsp_query.py def update_user_kkcoin
    python scripts/lsp_query.py hierarchy update_user_kkcoin
    python scripts/lsp_query.py symbols cogs/shop/shop.py
    python scripts/lsp_query.py diagnostics cogs/shop/shop.py
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent


def get_file_uri(file_path: str) -> str:
    """Convert file path to file:// URI."""
    path = Path(file_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve().as_uri()


def find_symbol_position(file_path: str, symbol: str) -> Optional[Dict[str, int]]:
    """Find the position of a symbol in a file by searching the content."""
    path = Path(file_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")

    for i, line in enumerate(lines):
        if symbol in line and not line.strip().startswith("#"):
            # Find column position
            col = line.index(symbol)
            return {"line": i, "character": col}

    return None


def cmd_refs(args):
    """Find all references to a symbol."""
    # This would use mcp_pylance_mcp_s_pylanceLSP with textDocument/references
    # For now, provide the command structure
    print("=== Find References ===")
    print(f"Symbol: {args.symbol}")
    print(f"File: {args.file}")
    print("\nThis command requires MCP Pylance LSP integration.")
    print("Use the MCP tool: mcp_pylance_mcp_s_pylanceLSP")
    print("Method: textDocument/references")
    print(
        "Params: { textDocument: { uri }, position: { line, character }, context: { includeDeclaration: true } }"
    )

    # Try to find position if file given
    if args.file:
        pos = find_symbol_position(args.file, args.symbol)
        if pos:
            print(f"\nFound at: line {pos['line']}, character {pos['character']}")
            print(f"File URI: {get_file_uri(args.file)}")


def cmd_def(args):
    """Find definition of a symbol."""
    print("=== Go to Definition ===")
    print(f"Symbol: {args.symbol}")
    print(f"File: {args.file}")
    print("\nMCP Tool: mcp_pylance_mcp_s_pylanceLSP")
    print("Method: textDocument/definition")
    print("Params: { textDocument: { uri }, position: { line, character } }")

    if args.file:
        pos = find_symbol_position(args.file, args.symbol)
        if pos:
            print(f"\nFound at: line {pos['line']}, character {pos['character']}")
            print(f"File URI: {get_file_uri(args.file)}")


def cmd_hierarchy(args):
    """Show call hierarchy (incoming/outgoing calls)."""
    print("=== Call Hierarchy ===")
    print(f"Symbol: {args.symbol}")
    print(f"File: {args.file}")
    print("\nMCP Tool: mcp_pylance_mcp_s_pylanceLSP")
    print("Methods:")
    print("  1. callHierarchy/prepare - get call hierarchy item")
    print("  2. callHierarchy/incomingCalls - who calls this")
    print("  3. callHierarchy/outgoingCalls - what this calls")
    print("Params: { textDocument: { uri }, position: { line, character } }")

    if args.file:
        pos = find_symbol_position(args.file, args.symbol)
        if pos:
            print(f"\nFound at: line {pos['line']}, character {pos['character']}")
            print(f"File URI: {get_file_uri(args.file)}")


def cmd_symbols(args):
    """List all symbols in a file."""
    print("=== Document Symbols ===")
    print(f"File: {args.file}")
    print("\nMCP Tool: mcp_pylance_mcp_s_pylanceLSP")
    print("Method: textDocument/documentSymbol")
    print(f"Params: {{ textDocument: {{ uri: '{get_file_uri(args.file)}' }} }}")

    # Also show file content summary
    path = Path(args.file)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if path.exists():
        content = path.read_text(encoding="utf-8")
        lines = content.split("\n")
        print(f"\nFile has {len(lines)} lines")
        # Quick grep for class/def
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("class ", "def ", "async def ")):
                print(f"  L{i+1}: {stripped[:80]}")


def cmd_diagnostics(args):
    """Get diagnostics (errors/warnings) for a file."""
    print("=== Diagnostics ===")
    print(f"File: {args.file}")
    print("\nMCP Tool: mcp_pylance_mcp_s_pylanceLSP")
    print("Method: textDocument/diagnostic")
    print(f"Params: {{ textDocument: {{ uri: '{get_file_uri(args.file)}' }} }}")
    print("\nOr use workspace/diagnostic for all files.")


def cmd_type(args):
    """Get type at position."""
    print("=== Type at Position ===")
    print(f"Symbol: {args.symbol}")
    print(f"File: {args.file}")
    print("\nMCP Tool: mcp_pylance_mcp_s_pylanceAnalyze")
    print("Command: typeAt")
    print("Params: { fileUri, position: { line, character } }")

    if args.file:
        pos = find_symbol_position(args.file, args.symbol)
        if pos:
            print(f"\nFound at: line {pos['line']}, character {pos['character']}")
            print(f"File URI: {get_file_uri(args.file)}")


def cmd_hover(args):
    """Get hover info at position."""
    print("=== Hover Info ===")
    print(f"Symbol: {args.symbol}")
    print(f"File: {args.file}")
    print("\nMCP Tool: mcp_pylance_mcp_s_pylanceLSP")
    print("Method: textDocument/hover")
    print("Params: { textDocument: { uri }, position: { line, character } }")

    if args.file:
        pos = find_symbol_position(args.file, args.symbol)
        if pos:
            print(f"\nFound at: line {pos['line']}, character {pos['character']}")
            print(f"File URI: {get_file_uri(args.file)}")


def main():
    parser = argparse.ArgumentParser(
        description="Query Pylance LSP for Python code intelligence"
    )
    parser.add_argument("--file", "-f", help="File path (relative to project root)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # refs
    p = subparsers.add_parser("refs", help="Find all references to a symbol")
    p.add_argument("symbol", help="Symbol name")

    # def
    p = subparsers.add_parser("def", help="Go to definition")
    p.add_argument("symbol", help="Symbol name")

    # hierarchy
    p = subparsers.add_parser("hierarchy", help="Call hierarchy (incoming/outgoing)")
    p.add_argument("symbol", help="Symbol name")

    # symbols
    p = subparsers.add_parser("symbols", help="List all symbols in a file")

    # diagnostics
    p = subparsers.add_parser("diagnostics", help="Get diagnostics for a file")

    # type
    p = subparsers.add_parser("type", help="Get inferred type at position")
    p.add_argument("symbol", help="Symbol name")

    # hover
    p = subparsers.add_parser("hover", help="Get hover info at position")
    p.add_argument("symbol", help="Symbol name")

    args = parser.parse_args()

    commands = {
        "refs": cmd_refs,
        "def": cmd_def,
        "hierarchy": cmd_hierarchy,
        "symbols": cmd_symbols,
        "diagnostics": cmd_diagnostics,
        "type": cmd_type,
        "hover": cmd_hover,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
