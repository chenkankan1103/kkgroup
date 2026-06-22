from pathlib import Path
workflow_path = Path('.github/workflows/ai-debug-monitor.yml')
output_path = Path('temp_ai_debug_check.py')
text = workflow_path.read_text(encoding='utf-8')
lines = text.splitlines()
out = []
inside = False
for line in lines:
    if line.strip() == "python <<'PY'":
        inside = True
        continue
    if inside and line.strip() == 'PY':
        break
    if inside:
        out.append(line[10:] if line.startswith('          ') else line)
output_path.write_text('\n'.join(out), encoding='utf-8')
print(f'Wrote {output_path} with {len(out)} lines')
