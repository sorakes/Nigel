import json
import re
import os

log_file = r'C:\Users\User\.gemini\antigravity-ide\brain\6a70953d-9c64-4019-96b5-6dbc577714b9\.system_generated\logs\transcript.jsonl'

files_recovered = set()

with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        if not line.strip(): continue
        obj = json.loads(line)
        if obj.get('type') == 'VIEW_FILE':
            content = obj.get('content', '')
            if 'File Path:' in content:
                # Extract file path
                try:
                    path_line = [l for l in content.split('\n') if l.startswith('File Path:')][0]
                    file_path = path_line.split('`')[1].replace('file:///', '')
                    
                    # Target path
                    if 'Documents/Seq' in file_path or 'Documents/Nigel' in file_path:
                        target = file_path.replace('Documents/Seq', 'Documents/Nigel')
                        target = os.path.normpath(target)
                        
                        if target in files_recovered:
                            continue
                            
                        # Extract code lines
                        code_lines = []
                        start_reading = False
                        for c_line in content.split('\n'):
                            if c_line.startswith('The following code has been modified'):
                                start_reading = True
                                continue
                            if c_line.startswith('The above content shows the entire'):
                                break
                            
                            if start_reading:
                                # Remove line numbers "1: ", "10: ", etc
                                m = re.match(r'^\d+:\s(.*)', c_line)
                                if m:
                                    code_lines.append(m.group(1))
                                else:
                                    # If empty line
                                    if re.match(r'^\d+:$', c_line):
                                        code_lines.append('')
                                        
                        if code_lines:
                            os.makedirs(os.path.dirname(target), exist_ok=True)
                            with open(target, 'w', encoding='utf-8') as tf:
                                tf.write('\n'.join(code_lines) + '\n')
                            print(f"Recovered {target} from VIEW_FILE")
                            files_recovered.add(target)
                except Exception as e:
                    print("Error parsing", e)
