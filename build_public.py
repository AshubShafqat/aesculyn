"""Create a source download from an explicit publication allowlist."""
from pathlib import Path
import zipfile
ROOT = Path(__file__).resolve().parent
FILES = ['.gitignore', 'README.md', 'requirements.txt', 'engine.py', 'server.py',
         'test_engine.py', 'build_public.py', 'VERIFICATION.md', 'PUBLICATION.md',
         '.github/workflows/pages.yml', 'research_predict.py', 'research_report.py',
         'test_research.py', 'test_research_integration.py', 'requirements-research-lock.txt', 'RESEARCH_RESULTS.md']
FILES += [str(p.relative_to(ROOT)) for p in (ROOT / 'research').glob('*.py')]
assets = [p for directory in ['static', 'public'] for p in (ROOT / directory).rglob('*')
          if p.is_file() and p.suffix in {'.html', '.css', '.js', '.svg', '.json'}]
with zipfile.ZipFile(ROOT / 'public/aesculyn-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in [ROOT / name for name in FILES] + assets:
        archive.write(path, path.relative_to(ROOT).as_posix())
print('Public source download built from allowlisted files.')
