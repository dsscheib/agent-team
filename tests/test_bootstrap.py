import contextlib
import importlib.util
import io
import json
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

    def test_second_install_adds_roles_and_keeps_original_backup(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p/'.codex').mkdir()
            (p/'.codex/config.toml').write_text('model = "original"\n')
            self.assertEqual(b.main(['--project',td,'--roles','backend','--apply']),0)
            self.assertEqual(b.main(['--project',td,'--roles','frontend','--apply']),0)
            parsed = tomllib.loads((p/'.codex/config.toml').read_text())
            self.assertIn('backend', parsed['agents'])
            self.assertIn('frontend', parsed['agents'])
            self.assertEqual((p/'.codex/config.toml.pre-agent-bootstrap.bak').read_text(),'model = "original"\n')

    def test_leftover_temp_file_stops_before_any_write(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p/'.codex').mkdir()
            (p/'.codex/config.toml.agent-bootstrap.tmp').write_text('stale')
            self.assertEqual(b.main(['--project',td,'--platforms','codex','claude','--roles','backend','--apply']),2)
            self.assertFalse((p/'.codex/agents').exists())
            self.assertFalse((p/'.claude').exists())
            self.assertFalse((p/'.codex/config.toml').exists())

    def test_inspectors_run_commands_but_do_not_edit(self):
        claude = b.claude_agent('frontend-tester')
        self.assertIn('Bash', claude)
        self.assertNotIn('Edit', claude.split('---')[1])
        self.assertIn('"execute"', b.copilot_agent('performance'))
        self.assertNotIn('"edit"', b.copilot_agent('performance'))
        self.assertIn('run_command', b.antigravity_agent('performance'))
        self.assertNotIn('replace_file_content', b.antigravity_agent('performance'))
        self.assertNotIn('sandbox_mode', b.codex_agent('performance'))
        self.assertIn('sandbox_mode = "read-only"', b.codex_agent('security'))
        self.assertNotIn('Bash', b.claude_agent('security').split('---')[1])

    def test_only_documented_tool_names(self):
        for role in b.ROLES:
            self.assertNotIn('find_by_name', b.antigravity_agent(role))
            fm = b.copilot_agent(role).split('---')[1]
            self.assertNotIn('"grep"', fm)
            self.assertNotIn('"glob"', fm)

    def test_frontmatter_survives_yaml_special_characters(self):
        saved = b.ROLES['backend']['description']
        try:
            b.ROLES['backend']['description'] = 'Owns APIs: auth, "quotes" and # hashes'
            for gen in (b.claude_agent, b.copilot_agent, b.antigravity_agent):
                line = [l for l in gen('backend').splitlines() if l.startswith('description: ')][0]
                self.assertEqual(json.loads(line[len('description: '):]), b.ROLES['backend']['description'])
        finally:
            b.ROLES['backend']['description'] = saved

    def test_list_does_not_need_project(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(b.main(['--list']),0)
        self.assertIn('inspector', out.getvalue())

    def test_missing_project_is_an_error(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            b.main(['--preset','core'])

if __name__=='__main__': unittest.main()
