import ast
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from tools import server_setup as setup

ROOT = Path(__file__).resolve().parents[1]


class ServerSetupTests(unittest.TestCase):
    def test_notebook_has_clean_outputs_and_compilable_cells(self):
        notebook = json.loads((ROOT / 'setup.ipynb').read_text(encoding='utf8'))
        self.assertEqual(notebook['nbformat'], 4)
        self.assertEqual(len({c['id'] for c in notebook['cells']}), len(notebook['cells']))
        sources = []
        for i, cell in enumerate(notebook['cells']):
            if cell['cell_type'] == 'code':
                self.assertIsNone(cell['execution_count'])
                self.assertEqual(cell['outputs'], [])
                source = ''.join(cell['source'])
                ast.parse(source, filename=f'setup.ipynb:cell{i}')
                sources.append(source)
        joined = '\n'.join(sources)
        for flag in ('INSTALL_PACKAGES = False', 'START_SERVER = False', 'STOP_SERVER = False'):
            self.assertIn(flag, joined)

    def test_app_root_requires_complete_source(self):
        self.assertEqual(setup.app_root(ROOT), ROOT)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                setup.app_root(directory)

    def test_offline_source_has_no_index(self):
        with tempfile.TemporaryDirectory() as directory:
            args = setup.pip_source(directory, 'https://example.org/simple')
            self.assertEqual(args, ['--no-index', '--find-links', str(Path(directory).resolve())])

    def test_package_index_cannot_embed_credentials_or_disable_tls(self):
        for index in ('http://example.org', 'https://user:secret@example.org/simple',
                      'https://example.org/simple?token=secret'):
            with self.assertRaises(ValueError):
                setup.pip_source(index=index)
        self.assertEqual(setup.pip_source(index='https://example.org/simple'),
                         ['--index-url', 'https://example.org/simple'])

    def test_install_is_opt_in(self):
        with patch.object(setup.subprocess, 'run') as run:
            setup.install_packages(ROOT)
        run.assert_not_called()

    def test_partial_torch_pair_is_not_repaired_by_guessing(self):
        versions = {key: None for key in setup.PRESERVE}
        versions['torch'] = '2.5.1+cu124'
        with patch.object(setup, 'installed_versions', return_value=versions), patch.object(setup.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, '하나만'):
                setup.install_packages(ROOT, enabled=True)
        run.assert_not_called()

    def test_missing_torch_needs_explicit_pair(self):
        versions = dict.fromkeys(setup.PRESERVE)
        with patch.object(setup, 'installed_versions', return_value=versions), patch.object(setup.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, '추측하지'):
                setup.install_packages(ROOT, enabled=True)
        run.assert_not_called()

    def test_existing_cuda_and_numpy_are_pinned_for_ocr(self):
        versions = dict.fromkeys(setup.PRESERVE)
        versions.update(torch='2.5.1+cu124', torchvision='0.20.1+cu124', numpy='1.26.4')
        commands = []
        def capture(command, **kwargs):
            commands.append(command)
            if 'install' in command:
                pinned = Path(command[command.index('-c') + 1]).read_text()
                self.assertIn('torch==2.5.1+cu124\n', pinned)
                self.assertIn('torchvision==0.20.1+cu124\n', pinned)
                self.assertIn('numpy==1.26.4\n', pinned)
                self.assertIn(str(ROOT / 'requirements-ocr.txt'), command)
                self.assertNotIn('--upgrade', command)
        with patch.object(setup, 'installed_versions', return_value=versions), patch.object(setup.subprocess, 'run', side_effect=capture):
            setup.install_packages(ROOT, enabled=True)
        self.assertEqual(len(commands), 2)  # one combined pip install, then pip check

    def test_new_torch_is_pinned_before_ocr_install(self):
        before = dict.fromkeys(setup.PRESERVE)
        after = dict(before, torch='2.5.1+cu124', torchvision='0.20.1+cu124')
        installs = []
        def capture(command, **kwargs):
            if 'install' in command:
                installs.append((command, Path(command[command.index('-c') + 1]).read_text()))
        with patch.object(setup, 'installed_versions', side_effect=[before, after, after]), patch.object(setup.subprocess, 'run', side_effect=capture):
            setup.install_packages(ROOT, enabled=True, torch_packages=['torch==2.5.1', 'torchvision==0.20.1'])
        self.assertEqual(len(installs), 2)
        self.assertIn('torch==2.5.1', installs[0][0])
        self.assertIn('torch==2.5.1+cu124', installs[1][1])

    def test_local_files_no_automatic_download(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / setup.SAM_NAMES['vit_h']
            with self.assertRaises(FileNotFoundError):
                setup.model_paths(ROOT, checkpoint=str(base), use_ocr=False)
            base.write_bytes(b'test-only-not-a-model')
            files = setup.model_paths(ROOT, checkpoint=str(base), use_ocr=False)
            self.assertEqual(files['checkpoint'], str(base.resolve()))
            self.assertIsNone(files['adaptation_path'])
            with self.assertRaises(FileNotFoundError):
                setup.model_paths(ROOT, checkpoint=str(base), ocr_dir=directory, use_ocr=True)
            for name in ('craft_mlt_25k.pth', 'english_g2.pth'):
                (Path(directory) / name).write_bytes(b'test')
            setup.model_paths(ROOT, checkpoint=str(base), ocr_dir=directory, use_ocr=True)

    def test_empty_adaptation_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / 'sam.pth'
            base.write_bytes(b'test')
            adapted = Path(directory) / 'adaptation.pt'
            adapted.touch()
            with self.assertRaises(FileNotFoundError):
                setup.model_paths(ROOT, checkpoint=str(base), adaptation=str(adapted), use_ocr=False)

    def test_sam2_variant_rejected(self):
        with self.assertRaises(ValueError):
            setup.model_paths(ROOT, variant='sam2')

    def test_port_conflict_does_not_launch_or_create_project(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            sock.listen()
            project = Path(directory) / 'not_created'
            server = setup.NotebookServer(ROOT, project, sock.getsockname()[1])
            with patch.object(setup.subprocess, 'Popen') as launch:
                with self.assertRaisesRegex(RuntimeError, '사용 중'):
                    server.start()
            launch.assert_not_called()
            self.assertFalse(project.exists())

    def test_stop_without_owned_process_is_noop(self):
        server = setup.NotebookServer(ROOT, 'projects/not-created')
        with patch.object(setup.subprocess, 'run') as run:
            self.assertTrue(server.stop())
            with self.assertRaises(RuntimeError):
                server.request('/api/state')
        run.assert_not_called()

    def test_invalid_port(self):
        for value in (0, 80, 65536, True, '8765'):
            with self.assertRaises(ValueError):
                setup.NotebookServer(ROOT, 'projects/test', value)


if __name__ == '__main__':
    unittest.main()
