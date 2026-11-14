import contextlib
import importlib.util
import io
import json
import os
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


b = load(ROOT / 'bootstrap.py')

class BootstrapTests(unittest.TestCase):
    def test_codex_agents_are_standalone_files(self):
        for role in b.ROLES:
            parsed = tomllib.loads(b.codex_agent(role))
            self.assertEqual(parsed['name'], role)
            self.assertEqual(parsed['description'], b.ROLES[role]['description'])
            self.assertIn('developer_instructions', parsed)
            self.assertNotIn('sandbox_mode', parsed)
            runs = b.caps(role)['run']
            self.assertEqual(parsed.get('features', {}).get('shell_tool', True), runs)

    def test_leaves_codex_config_and_existing_agents_alone(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p/'.codex/agents').mkdir(parents=True)
            config = 'model = "custom-parent"\n[agents]\nmax_threads = 2\n'
            (p/'.codex/config.toml').write_text(config)
            (p/'.codex/agents/existing.toml').write_text('name = "existing"\n')
            args = ['--project',td,'--platforms','codex','claude','copilot','antigravity','--roles','backend','auditor-advisor','--apply']
            self.assertEqual(b.main(args),0)
            self.assertEqual((p/'.codex/config.toml').read_text(), config)
            self.assertEqual((p/'.codex/agents/existing.toml').read_text(),'name = "existing"\n')
            for path in ('.codex/agents/backend.toml', '.github/agents/auditor-advisor.agent.md',
                         '.agents/agents/auditor-advisor.md', '.claude/agents/auditor-advisor.md'):
                self.assertTrue((p/path).exists(), path)
            self.assertFalse(any(p.glob('.codex/*.bak')))
            self.assertEqual(b.main(args),0)

    def test_second_install_adds_roles(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            self.assertEqual(b.main(['--project',td,'--roles','backend','--apply']),0)
            self.assertEqual(b.main(['--project',td,'--roles','backend','frontend','--apply']),0)
            self.assertEqual(sorted(f.name for f in (p/'.codex/agents').iterdir()), ['backend.toml','frontend.toml'])

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(b.main(['--project',td,'--preset','core']),0)
            self.assertEqual(list(Path(td).iterdir()),[])

    def test_conflicts_do_not_change_project(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/'.claude/agents').mkdir(parents=True)
            conflict=p/'.claude/agents/backend.md'
            conflict.write_text('custom')
            self.assertEqual(b.main(['--project',td,'--platforms','claude','--roles','backend','frontend','--apply']),2)
            self.assertFalse((p/'.claude/agents/frontend.md').exists())
            self.assertEqual(conflict.read_text(),'custom')

    def test_inspectors_run_commands_but_do_not_edit(self):
        claude = b.claude_agent('frontend-tester')
        self.assertIn('Bash', claude)
        self.assertNotIn('Edit', claude.split('---')[1])
        self.assertIn('"execute"', b.copilot_agent('performance'))
        self.assertNotIn('"edit"', b.copilot_agent('performance'))
        self.assertIn('run_command', b.antigravity_agent('performance'))
        self.assertNotIn('replace_file_content', b.antigravity_agent('performance'))
        self.assertNotIn('shell_tool', b.codex_agent('performance'))
        self.assertIn('shell_tool = false', b.codex_agent('security'))
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

    def test_catalog_domains_and_presets_are_consistent(self):
        self.assertEqual(set(b.ROLES), set(b.DETAILS))
        for role, info in b.ROLES.items():
            self.assertIn(info['domain'], b.DOMAIN_DIRS, role)
            b.caps(role)
        for name, members in b.PRESETS.items():
            self.assertTrue(set(members) <= set(b.ROLES), name)
        self.assertEqual({b.ROLES[r]['domain'] for r in b.PRESETS['full']}, {'software'})

    def test_domain_roles_get_domain_practices(self):
        self.assertIn('KiCad 10 electronics operating principles', b.body('pcb-layout'))
        self.assertIn('FreeCAD mechanical', b.body('cad-verifier'))
        self.assertNotIn('Never assume a language, framework', b.body('pcb-layout'))
        self.assertIn('Never assume a language, framework', b.body('backend'))
        self.assertIn('review-only', b.body('hardware-auditor'))
        self.assertIn('shell_tool = false', b.codex_agent('mechanical-auditor'))
        self.assertNotIn('Edit', b.claude_agent('cad-verifier').split('---')[1])
        self.assertIn('Bash', b.claude_agent('cad-verifier').split('---')[1])

    def test_hardware_and_mechanical_install_on_all_platforms(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            args = ['--project', td, '--platforms', 'codex', 'claude', 'copilot', 'antigravity',
                    '--preset', 'kicad-core', 'freecad-core', '--with-tools', '--with-agents-md', '--apply']
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(args), 0)
            for role in b.PRESETS['kicad-core'] + b.PRESETS['freecad-core']:
                for path in (f'.codex/agents/{role}.toml', f'.claude/agents/{role}.md',
                             f'.github/agents/{role}.agent.md', f'.agents/agents/{role}.md'):
                    self.assertTrue((p/path).is_file(), path)
            for tool in ('tools/kicad/verify.py', 'tools/kicad/fabrication_export.py', 'tools/freecad/inspect_model.py',
                         'tools/freecad/check_build_volume.py', 'docs/electronics/release-checklist.md',
                         'docs/mechanical/slicing.md', 'scripts/create_parametric_plate.py'):
                self.assertTrue((p/tool).is_file(), tool)
            self.assertTrue(os.access(p/'tools/kicad/verify.py', os.X_OK))
            agents = (p/'AGENTS.md').read_text()
            self.assertIn('## Electronics (KiCad)', agents)
            self.assertIn('## Mechanical (FreeCAD)', agents)
            self.assertNotIn('## Tech stack', agents)
            self.assertFalse((p/'.codex/config.toml').exists())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(args), 0)

    def test_tools_only_with_flag_and_only_for_selected_domains(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(['--project', td, '--preset', 'kicad-core', '--apply']), 0)
            self.assertFalse((p/'tools').exists())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(['--project', td, '--preset', 'kicad-core', '--with-tools', '--apply']), 0)
            self.assertTrue((p/'tools/kicad').is_dir())
            self.assertFalse((p/'tools/freecad').exists())

    def test_mixed_agents_md_keeps_software_starter(self):
        text = b.agents_md(['backend', 'cad-engineer'])
        self.assertIn('## Tech stack', text)
        self.assertIn('## Mechanical (FreeCAD)', text)
        self.assertEqual(b.agents_md(['backend']), b.STARTER_AGENTS_MD)

    def test_kicad_verify_checks_only_root_schematics(self):
        verify = load(ROOT/'domains/kicad/files/tools/kicad/verify.py')
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            for name in ('board.kicad_pro', 'board.kicad_sch', 'board.kicad_pcb', 'subsheet.kicad_sch'):
                (p/name).write_text('')
            self.assertEqual([(c, s.name) for _, c, s in verify.checks(p)],
                             [('erc', 'board.kicad_sch'), ('drc', 'board.kicad_pcb')])

    def test_kicad_doctor_prefers_kicad_python_env_then_default_venv(self):
        doctor = load(ROOT/'domains/kicad/files/tools/kicad/doctor.py')
        with tempfile.TemporaryDirectory() as td:
            custom = Path(td)/'python'
            custom.write_text('')
            saved = os.environ.get('KICAD_PYTHON')
            try:
                os.environ['KICAD_PYTHON'] = str(custom)
                found = doctor.kipy_interpreters()
            finally:
                if saved is None:
                    os.environ.pop('KICAD_PYTHON')
                else:
                    os.environ['KICAD_PYTHON'] = saved
            self.assertEqual(found[0], str(custom))
            self.assertEqual(found[-1], doctor.sys.executable)
            self.assertTrue(str(doctor.DEFAULT_VENV_PYTHON).endswith('.local/share/kicad-python/bin/python'))

    def test_build_volume_check(self):
        check = load(ROOT/'domains/freecad/files/tools/freecad/check_build_volume.py')
        with tempfile.TemporaryDirectory() as td:
            report = Path(td)/'r.json'
            report.write_text(json.dumps({'shapes': [{'object': 'Pad', 'envelope_mm': [250, 60, 3]}]}))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(check.main([str(report)]), 0)  # fits when rotated onto Z
                self.assertEqual(check.main([str(report), '--volume', '200', '200', '200']), 2)

    def test_domain_scripts_compile(self):
        for script in (ROOT/'domains').rglob('*.py'):
            compile(script.read_text(), str(script), 'exec')

if __name__=='__main__': unittest.main()
