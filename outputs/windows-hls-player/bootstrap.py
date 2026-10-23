"""Small native bundle launcher; media JIT runs in the unmodified private runtime."""
import os,sys,subprocess
from pathlib import Path
def main():
    home=Path(sys.executable).resolve().parent
    env=os.environ.copy();env['XUPERPC_PORTABLE_ROOT']=str(home);env['XUPERPC_ENGINE_ROOT']=str(home/'Engine')
    env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
    command=[str(home/'Engine/python.exe'),'-I',str(home/'Engine/app/portable.py'),*sys.argv[1:]]
    process=subprocess.Popen(command,cwd=home,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    return process.wait() if '--self-test' in sys.argv else 0
if __name__=='__main__':sys.exit(main())
