"""Per-installation playback language preferences; no session data."""
import json,threading
from pathlib import Path
DEFAULT={'general':{'audio':'original','subtitle':'off'},'anime':{'audio':'ja','subtitle':'es'}}
LANGUAGES={'es','en','ja','ko','zh','pt','fr','de','it'}
class Preferences:
 def __init__(self,root):self.path=Path(root)/'work/library/preferences.json';self.lock=threading.RLock()
 def validate(self,value):
  result={}
  for group in DEFAULT:
   row=value.get(group)
   if not isinstance(row,dict) or row.get('audio') not in LANGUAGES|{'original','default'} or row.get('subtitle') not in LANGUAGES|{'off'}:raise ValueError('Preferencias de idioma no válidas.')
   result[group]={'audio':row['audio'],'subtitle':row['subtitle']}
  return result
 def read(self):
  with self.lock:
   try:return self.validate(json.loads(self.path.read_text(encoding='utf8')))
   except (OSError,ValueError,TypeError,AttributeError):return json.loads(json.dumps(DEFAULT))
 def save(self,value):
  result=self.validate(value)
  with self.lock:
   self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(result),encoding='utf8');temp.replace(self.path)
  return result
