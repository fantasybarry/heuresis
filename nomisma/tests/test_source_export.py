import unittest

from tools.export_source import allowed_source


class SourceExportTests(unittest.TestCase):
    def test_source_archive_excludes_credentials_history_and_personal_data(self):
        for name in ("nomisma/.env", "nomisma/.env.local", "nomisma/data/nomisma.sqlite3",
                     "nomisma/data/import.csv", "nomisma/backups/research.sqlite3", ".git/config",
                     "nomisma/dist/Nomisma.exe", "nomisma/build/toolchains/private.json",
                     "nomisma/desktop/windows/obj/project.assets.json", "nomisma/research.db",
                     "nomisma/static/.secret.json", "nomisma/private-research.csv", "../private.json", "/private.json"):
            with self.subTest(name=name):
                self.assertFalse(allowed_source(name))

    def test_source_archive_preserves_root_workflow_and_windows_build_inputs(self):
        for name in (".github/workflows/nomisma-windows.yml", "README.md", ".gitignore", "nomisma/.gitignore",
                     "nomisma/.env.example", "nomisma/desktop/windows/Nomisma.Windows.csproj",
                     "nomisma/desktop/windows/packages.lock.json", "nomisma/desktop/windows/installer.nsi",
                     "nomisma/desktop/windows/app.manifest", "nomisma/examples/prices.csv",
                     "nomisma/tools/build_windows.py", "nomisma/nomisma/static/live.js"):
            with self.subTest(name=name):
                self.assertTrue(allowed_source(name))
