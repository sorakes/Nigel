import json
import glob
import os

brain_dir = r"C:\Users\User\.gemini\antigravity-ide\brain"
log_files = [r"C:\Users\User\.gemini\antigravity-ide\brain\6a70953d-9c64-4019-96b5-6dbc577714b9\.system_generated\logs\transcript.jsonl"]

events = []
for lf in log_files:
    try:
        with open(lf, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                obj = json.loads(line)
                if obj.get('type') == 'PLANNER_RESPONSE':
                    created_at = obj.get('created_at', '')
                    for tc in obj.get('tool_calls', []):
                        if tc['name'] in ('write_to_file', 'replace_file_content', 'multi_replace_file_content'):
                            events.append({'time': created_at, 'tool': tc['name'], 'args': tc['args']})
    except Exception as e:
        print("Error reading", lf, e)

events.sort(key=lambda x: x['time'])

file_state = {}

for ev in events:
    args = ev['args']
    target = args.get('TargetFile')
    if not target: continue
    
    # Ignore artifacts and scratch files
    if '.gemini' in target or '.antigravity' in target:
        continue
    
    target = target.replace("Documents/Seq", "Documents/Nigel").replace("Documents\\Seq", "Documents\\Nigel")
    target = os.path.normpath(target)
    
    if ev['tool'] == 'write_to_file':
        code = args.get('CodeContent', '')
        file_state[target] = code
    elif ev['tool'] == 'replace_file_content':
        if target in file_state:
            old = args.get('TargetContent', '')
            new = args.get('ReplacementContent', '')
            file_state[target] = file_state[target].replace(old, new)
    elif ev['tool'] == 'multi_replace_file_content':
        if target in file_state:
            chunks = args.get('ReplacementChunks', [])
            if isinstance(chunks, str):
                try:
                    chunks = json.loads(chunks)
                except Exception:
                    chunks = []
            code = file_state[target]
            for chunk in chunks:
                old = chunk.get('TargetContent', '')
                new = chunk.get('ReplacementContent', '')
                code = code.replace(old, new)
            file_state[target] = code

restored_count = 0
for filepath, code in file_state.items():
    if not filepath.endswith('.py'): continue
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)
    print(f"Restored {filepath}")
    restored_count += 1

print(f"Total files restored: {restored_count}")
