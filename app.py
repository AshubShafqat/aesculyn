"""Start Aesculyn with optional private Render model artifacts."""
import base64,io,json,os,tempfile,zipfile
from pathlib import Path

def load_render_models():
    secret=Path('/etc/secrets/aesculyn-modelstore.zip.b64')
    if not secret.is_file(): return
    encoded=secret.read_bytes().strip()
    if not encoded or len(encoded)>1_000_000: raise RuntimeError('Invalid Render model bundle size.')
    try: payload=base64.b64decode(encoded,validate=True)
    except Exception as exc: raise RuntimeError('Render model bundle must be valid base64.') from exc
    if len(payload)>750_000: raise RuntimeError('Decoded model bundle is too large.')
    destination=Path(tempfile.gettempdir())/'aesculyn-modelstore'
    destination.mkdir(mode=0o700,parents=True,exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names=archive.namelist()
            if not names or len(names)>8 or any(Path(n).name!=n or n in ('','.','..') for n in names):
                raise RuntimeError('Unsafe model bundle paths.')
            if 'registry.json' not in names: raise RuntimeError('Model bundle is missing registry.json.')
            manifest=json.loads(archive.read('registry.json'));expected={'registry.json'}
            for model in manifest.get('models',[]):
                for key in ('file','preprocessing_file'):
                    name=model.get(key,'')
                    if not name or Path(name).name!=name: raise RuntimeError('Unsafe path in model registry.')
                    expected.add(name)
            if set(names)!=expected or len(expected)<2: raise RuntimeError('Bundle files do not match the registry.')
            if sum(item.file_size for item in archive.infolist())>2_000_000 or archive.testzip() is not None:
                raise RuntimeError('Model ZIP failed integrity or size checks.')
            for name in names: (destination/name).write_bytes(archive.read(name))
    except (OSError,ValueError,KeyError,zipfile.BadZipFile) as exc:
        raise RuntimeError('Could not load Render model bundle.') from exc
    os.environ['AESCULYN_MODELS']=str(destination)

if __name__=='__main__':
    load_render_models()
    if not os.environ.get('AESCULYN_PUBLIC_URL') and os.environ.get('RENDER_EXTERNAL_URL'):
        os.environ['AESCULYN_PUBLIC_URL']=os.environ['RENDER_EXTERNAL_URL']
    if os.environ.get('RENDER') and not Path('/etc/secrets/aesculyn-modelstore.zip.b64').is_file():
        raise SystemExit('Add the private aesculyn-modelstore.zip.b64 secret before deployment.')
    from application.http import main
    main()
