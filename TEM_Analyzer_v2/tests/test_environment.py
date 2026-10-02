import contextlib
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import check_environment


class EnvironmentTests(unittest.TestCase):
    def test_missing_packages_have_install_hint_without_network(self):
        out=io.StringIO()
        with patch.object(check_environment.importlib.util,'find_spec',return_value=None),contextlib.redirect_stdout(out):
            self.assertFalse(check_environment.check())
        self.assertIn('uvicorn',out.getvalue());self.assertIn('install_windows.bat',out.getvalue())

    def test_launcher_without_site_packages_reports_missing_uvicorn(self):
        root=Path(__file__).resolve().parents[1]
        r=subprocess.run([sys.executable,'-S',str(root/'run.py')],cwd=root,capture_output=True,text=True)
        self.assertEqual(r.returncode,1);self.assertIn('uvicorn',r.stdout);self.assertNotIn('Traceback',r.stderr)
