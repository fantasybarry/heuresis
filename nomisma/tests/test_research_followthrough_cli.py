import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location('research_followthrough', Path(__file__).resolve().parents[1]/'tools/research_followthrough.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class CheckpointTests(unittest.TestCase):
    def fixture(self, root):
        candidate = {'id': 'policy-a', 'config': {'policy': {'hold_minutes': 15}}}
        path = Path(root)/candidate['id']; path.mkdir()
        for name, value in [('config.json', candidate['config']), ('metrics.json', {}),
                            ('result.json', {'config': candidate['config'], 'run_fingerprint': 'fixed'})]:
            (path/name).write_text(json.dumps(value))
        digest = hashlib.sha256(json.dumps(candidate['config'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        manifest = {'config_sha256': digest, 'identity': {'policy_id': candidate['id'], 'config_sha256': digest},
                    'result_run_fingerprint': 'fixed'}
        for name, key in [('config.json', 'config_file_sha256'), ('result.json', 'result_sha256'), ('metrics.json', 'metrics_sha256')]:
            manifest[key] = hashlib.sha256((path/name).read_bytes()).hexdigest()
        (path/'manifest.json').write_text(json.dumps(manifest))
        return candidate, path

    def test_hash_verified_checkpoint_and_read_only(self):
        with tempfile.TemporaryDirectory() as root:
            candidate, path = self.fixture(root)
            before = {p.name: p.read_bytes() for p in path.iterdir()}
            result, provenance = cli.verified_legacy_candidate(root, candidate)
            self.assertEqual(result['config'], candidate['config'])
            self.assertEqual(provenance['id'], candidate['id'])
            self.assertEqual(before, {p.name: p.read_bytes() for p in path.iterdir()})

    def test_mutated_result_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            candidate, path = self.fixture(root)
            (path/'result.json').write_text('{}')
            with self.assertRaises(ValueError): cli.verified_legacy_candidate(root, candidate)

    def test_valid_bytes_wrong_policy_configuration_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            candidate, unused = self.fixture(root)
            candidate['config']['policy']['hold_minutes'] = 30
            with self.assertRaises(ValueError): cli.verified_legacy_candidate(root, candidate)


if __name__ == '__main__': unittest.main()
