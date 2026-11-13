import importlib.util
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bootstrap', ROOT / 'bootstrap.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

class BootstrapTests(unittest.TestCase):
    def test_all_generated_toml_parses(self):
        for role in b.ROLES:
            self.assertEqual(tomllib.loads(b.codex_agent(role))['model'], b.ROLES[role]['codex_model'])
            self.assertEqual(tomllib.loads(b.codex_registration(role))['agents'][role]['config_file'], f'./agents/{role}.toml')

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(b.main(['--project',td,'--preset','core']),0)
            self.assertEqual(list(Path(td).iterdir()),[])

    def test_preserves_config_and_existing_agents(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p/'.codex/agents').mkdir(parents=True)
            (p/'.codex/config.toml').write_text('model = "custom-parent"\n[agents.existing]\ndescription="Existing"\nconfig_file="./agents/existing.toml"\n')
            (p/'.codex/agents/existing.toml').write_text('model = "custom"\n')
            self.assertEqual(b.main(['--project',td,'--platforms','codex','claude','copilot','antigravity','--roles','backend','auditor-advisor','--apply']),0)
            parsed=tomllib.loads((p/'.codex/config.toml').read_text())
            self.assertEqual(parsed['model'],'custom-parent')
            self.assertEqual(parsed['agents']['existing']['description'],'Existing')
            self.assertIn('backend',parsed['agents'])
            self.assertEqual((p/'.codex/agents/existing.toml').read_text(),'model = "custom"\n')
            self.assertTrue((p/'.codex/config.toml.pre-agent-bootstrap.bak').exists())
            self.assertTrue((p/'.github/agents/auditor-advisor.agent.md').exists())
            self.assertTrue((p/'.agents/agents/auditor-advisor.md').exists())
            self.assertTrue((p/'.claude/agents/auditor-advisor.md').exists())
            self.assertEqual(b.main(['--project',td,'--platforms','codex','claude','copilot','antigravity','--roles','backend','auditor-advisor','--apply']),0)

    def test_conflicts_do_not_change_project(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/'.claude/agents').mkdir(parents=True)
            conflict=p/'.claude/agents/backend.md'
            conflict.write_text('custom')
            self.assertEqual(b.main(['--project',td,'--platforms','claude','--roles','backend','frontend','--apply']),2)
            self.assertFalse((p/'.claude/agents/frontend.md').exists())
            self.assertEqual(conflict.read_text(),'custom')

if __name__=='__main__': unittest.main()
