"""Replace generated files only after their complete contents are written."""
import os
import tempfile
from pathlib import Path


def atomic_write(path, contents):
    path = Path(path)
    data = contents.encode('utf-8') if isinstance(contents, str) else contents
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '-')
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
