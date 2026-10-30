import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'outputs/windows-hls-player'))
from preferences import Preferences
class Tests(unittest.TestCase):
 def test_save_restore_and_validation(self):
  with tempfile.TemporaryDirectory(dir='work') as directory:
   store=Preferences(directory);self.assertEqual(store.read()['anime'],{'audio':'ja','subtitle':'es'})
   value={'general':{'audio':'es','subtitle':'off'},'anime':{'audio':'ja','subtitle':'es'}};store.save(value)
   self.assertEqual(Preferences(directory).read(),value)
   with self.assertRaises(ValueError):store.save({'general':{'audio':'bad','subtitle':'es'},'anime':value['anime']})
   self.assertEqual(store.read(),value)
if __name__=='__main__':unittest.main()
