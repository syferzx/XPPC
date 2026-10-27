import ast,collections,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
source=ast.parse(Path('outputs/windows-hls-player/portal.py').read_text(encoding='utf8'))
klass=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='PortalService')
method=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='title_detail')
namespace={'time':time}
exec(compile(ast.Module(body=[method],type_ignores=[]),'portal.py','exec'),namespace)
class Portal:
    title_detail=namespace['title_detail']
    def __init__(self):
        self.lock=threading.RLock();self.title_details=collections.OrderedDict();self.assets={str(i):('movies',{'contentId':str(i)}) for i in range(70)};self.calls=0;self.valid=True
    def request(self,*args):
        self.calls+=1
        return {'assetData':{'simpleProgramList':[{'contentId':'program'}]}} if self.valid else {}
class Tests(unittest.TestCase):
    def test_reuse_expiry_and_limit(self):
        p=Portal()
        with patch.object(time,'monotonic',return_value=10):
            a=p.title_detail('0');self.assertIs(a,p.title_detail('0'));self.assertEqual(p.calls,1)
        with patch.object(time,'monotonic',return_value=71):p.title_detail('0')
        self.assertEqual(p.calls,2)
        for i in range(70):p.title_detail(str(i))
        self.assertEqual(len(p.title_details),64)
    def test_invalid_not_cached(self):
        p=Portal();p.valid=False
        with self.assertRaises(ValueError):p.title_detail('0')
        self.assertFalse(p.title_details)
unittest.main()
