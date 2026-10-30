"""Create a new local portable using an existing runtime and current client sources."""
import argparse,ast,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--rebuild-launcher',action='store_true')
    args=parser.parse_args();base=args.base.resolve();out=args.output.resolve()
    if out.exists():parser.error('La carpeta de salida debe ser nueva.')
    if out.is_relative_to(base) or base.is_relative_to(out):parser.error('Usa carpetas separadas para la base y la salida.')
    for name in ('Engine','_internal','XuperPC.exe'):
        if not (base/name).exists():parser.error('Portable incompleto: falta '+name)
    app=ROOT/'outputs/windows-hls-player'
    sources=list(app.glob('*.py'))+list((ROOT/'work').glob('*.py'))+[ROOT/'outputs/ranger-windows/slb_protocol.py']
    for file in sources:ast.parse(file.read_text(encoding='utf-8-sig'),filename=file.name)
    out.mkdir(parents=True)
    def copy(source,target):
        target.parent.mkdir(parents=True,exist_ok=True)
        if source.is_dir():shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('Datos','__pycache__','*.pyc','*.private.*','*.log'))
        else:shutil.copy2(source,target)
    for name in ('Engine','_internal','XuperPC.exe'):copy(base/name,out/name)
    for file in sources:
        if not file.name.startswith('test_') and file.name!='bootstrap.py':copy(file,out/'Engine/app'/file.name)
    for name in ('index.html','app.css','player.js','library.js','downloads.js','preferences.js','vendor','assets'):copy(app/name,out/'Engine/app'/name)
    for name in ('app-bootstrap.json','rutas-portal.json'):copy(ROOT/'outputs'/name,out/'Engine/outputs'/name)
    copy(app/'PORTABLE.txt',out/'LEEME.txt')
    copy(app/'Iniciar.bat',out/'Iniciar.bat')
    for name in ('LICENSE','THIRD_PARTY_NOTICES.md','LICENSES'):copy(ROOT/name,out/'Documentacion'/name)
    if args.rebuild_launcher:
        subprocess.run([sys.executable,'-m','PyInstaller',str(app/'bootstrap.py'),'--name','XuperPC','--onedir','--windowed','--noupx','--icon',str(app/'assets/xuperpc.ico'),'--distpath',str(out.parent/'launcher-dist'),'--workpath',str(out.parent/'launcher-build'),'--specpath',str(out.parent/'launcher-build')],check=True)
        built=out.parent/'launcher-dist/XuperPC'
        copy(built/'XuperPC.exe',out/'XuperPC.exe');copy(built/'_internal',out/'_internal')
    print('Portable preparado en: '+str(out))
if __name__=='__main__':main()
