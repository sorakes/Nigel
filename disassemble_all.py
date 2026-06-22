import os
import dis
import marshal
import sys

def disassemble_pyc(filepath):
    try:
        with open(filepath, 'rb') as f:
            f.seek(16)
            code = marshal.load(f)
            
        out_path = filepath + '.dis.txt'
        with open(out_path, 'w', encoding='utf-8') as out:
            import io
            old_stdout = sys.stdout
            sys.stdout = out
            try:
                dis.dis(code)
            finally:
                sys.stdout = old_stdout
        print(f"Disassembled {filepath} -> {out_path}")
    except Exception as e:
        print(f"Error disassembling {filepath}: {e}")

if __name__ == '__main__':
    for root, dirs, files in os.walk('.'):
        if 'venv' in root:
            continue
        for file in files:
            if file.endswith('.pyc'):
                disassemble_pyc(os.path.join(root, file))
