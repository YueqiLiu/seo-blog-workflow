import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seo_blog_workflow.files import atomic_write


class FileTests(unittest.TestCase):
    def test_failed_replacement_preserves_original_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'index.md'
            path.write_text('original')
            with patch('seo_blog_workflow.files.os.replace', side_effect=OSError):
                with self.assertRaises(OSError):
                    atomic_write(path, 'new content')
            self.assertEqual(path.read_text(), 'original')
            self.assertEqual(list(Path(folder).iterdir()), [path])
