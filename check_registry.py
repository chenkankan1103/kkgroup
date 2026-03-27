import agent_tools

print("Registered tools in _TOOL_REGISTRY:")
print(f"Total: {len(agent_tools._TOOL_REGISTRY)}")

for name in sorted(agent_tools._TOOL_REGISTRY.keys()):
    spec = agent_tools._TOOL_REGISTRY[name]["spec"]
    print(f"  - {name}: {spec.get('description', 'N/A')[:50]}...")

print("\nChecking for Git tools:")
git_tools = [name for name in agent_tools._TOOL_REGISTRY if 'project_file' in name or 'git_status' in name]
print(f"Found {len(git_tools)} Git-related tools: {git_tools}")
