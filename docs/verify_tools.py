import agent_tools

print("✓ Tools imported successfully")
tools = agent_tools.get_gemini_tools_spec()
print(f"✓ Total {len(tools)} tools registered")
print("\nLast 3 tools:")
for tool in tools[-3:]:
    print(f"  - {tool['name']}: {tool['description'][:60]}...")
