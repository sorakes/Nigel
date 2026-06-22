import json
import re
from ui.agenda_skills import parse_skills_json

text = '''Aqui está a resposta.
```json
{
  "actions": [
    {"type": "save_memory", "category": "persona", "subject": "Leonardo", "note": "Amigo do usuário"}
  ]
}
```
'''
print("PARSE 1:", parse_skills_json(text))

text2 = '''{"actions": [{"type": "save_memory", "category": "persona", "subject": "Leonardo", "note": "Amigo do usuário"}]}'''
print("PARSE 2:", parse_skills_json(text2))
