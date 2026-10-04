"""Create a clean roll-number ZIP; refuse incomplete metadata unless --draft."""
import argparse
import json
import re
import subprocess
import zipfile
from pathlib import Path

EXCLUDED={'.git','.venv','venv','node_modules','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache'}
METADATA={'SUBMISSION.md','submission_details.json'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--draft',action='store_true')
    p.add_argument('--output')
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    details=json.loads((root/'submission_details.json').read_text(encoding='utf-8'))
    if details['status']!='final' and not args.draft:
        p.error('Metadata is incomplete. Use --draft only for a clearly labelled review package.')
    def git(*command):
        return subprocess.check_output(['git','-C',str(root),*command],text=True).strip()
    source_commit=details['source_commit']
    if not re.fullmatch(r'[0-9a-f]{40}',source_commit):
        p.error('Declared source_commit must be a full commit hash.')
    if subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',source_commit,'HEAD'],capture_output=True).returncode:
        p.error('Declared source_commit is not an ancestor of HEAD.')
    if any(name not in METADATA for name in git('diff',source_commit,'HEAD','--name-only').splitlines()):
        p.error('HEAD contains source changes after the declared source commit.')
    # Metadata may be generated after the source commit, as the supplied starter permits.
    changed=git('diff','HEAD','--name-only').splitlines()
    if any(name not in METADATA for name in changed):
        p.error('Commit source/evidence changes before packaging.')
    source_paths=git('ls-files').splitlines()
    tracked=set(source_paths)
    if any(name not in METADATA for name in git('ls-files','--others','--exclude-standard').splitlines()):
        p.error('Untracked source/evidence must be committed before packaging.')
    output=Path(args.output) if args.output else root.parent/'i221296.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(tracked | METADATA):
            path=root/relative
            if not path.is_file(): continue
            if any(part in EXCLUDED for part in Path(relative).parts): continue
            if path.name.startswith('.env') and path.name!='.env.example': continue
            if path.suffix.lower() in ('.zip','.pyc','.log'): continue
            if path.suffix.lower() in ('.pem','.key','.p12','.pfx'):
                raise RuntimeError('Private key/certificate file excluded; inspect source before submission.')
            archive.write(path,'i221296/'+relative)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip(): raise RuntimeError('ZIP integrity check failed')
        assert all(n.startswith('i221296/') for n in archive.namelist())
        assert 'i221296/SUBMISSION.md' in archive.namelist()
    print(str(output))

if __name__=='__main__': main()
