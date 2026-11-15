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
            for tool in ('tools/kicad/verify.py', 'tools/kicad/fabrication_export.py', 'tools/kicad/check_availability.py',
                         'tools/freecad/inspect_model.py',
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

    def test_existing_agents_md_gets_missing_domain_sections_once(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p/'AGENTS.md').write_text('# Agent instructions\n\nProject rules.')
            args = ['--project', td, '--preset', 'kicad-core', '--with-agents-md', '--apply']
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(args), 0)
            text = (p/'AGENTS.md').read_text()
            self.assertTrue(text.startswith('# Agent instructions\n\nProject rules.\n\n## Electronics (KiCad)'))
            self.assertNotIn('## Tech stack', text)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(args), 0)
                self.assertEqual(b.main(args[:-1] + ['--roles', 'cad-engineer', '--apply']), 0)
            text = (p/'AGENTS.md').read_text()
            self.assertEqual(text.count('## Electronics (KiCad)'), 1)
            self.assertEqual(text.count('## Mechanical (FreeCAD)'), 1)

    def test_tools_keep_reports_out_of_git(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(['--project', td, '--preset', 'kicad-core', '--with-tools', '--apply']), 0)
            self.assertEqual((p/'.gitignore').read_text(), b.GITIGNORE_BLOCK)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p/'.gitignore').write_text('node_modules/')
            args = ['--project', td, '--preset', 'freecad-core', '--with-tools', '--apply']
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(args), 0)
                self.assertEqual(b.main(args), 0)
            self.assertEqual((p/'.gitignore').read_text(), 'node_modules/\n\n' + b.GITIGNORE_BLOCK)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p/'.gitignore').write_text('/reports\n')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(['--project', td, '--preset', 'kicad-core', '--with-tools', '--apply']), 0)
            self.assertEqual((p/'.gitignore').read_text(), '/reports\n')
        with tempfile.TemporaryDirectory() as td:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(['--project', td, '--preset', 'core', '--with-tools', '--apply']), 0)
            self.assertFalse((Path(td)/'.gitignore').exists())

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

    def test_availability_credentials_env_wins_and_files_fill_gaps(self):
        avail = load(ROOT/'domains/kicad/files/tools/kicad/check_availability.py')
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d/'digikey.env').write_text('DIGIKEY_CLIENT_ID=file-id\nexport DIGIKEY_CLIENT_SECRET="file-secret"\n# c\n')
            (d/'mouser.env').write_text('MOUSER_API_KEY=file-key\nUNRELATED=x\n')
            for f in d.iterdir():
                f.chmod(0o600)
            creds, warnings = avail.load_credentials(d, {'DIGIKEY_CLIENT_ID': 'env-id'})
            self.assertEqual(creds, {'DIGIKEY_CLIENT_ID': 'env-id', 'DIGIKEY_CLIENT_SECRET': 'file-secret',
                                     'MOUSER_API_KEY': 'file-key'})
            self.assertEqual(warnings, [])
            (d/'mouser.env').chmod(0o644)
            self.assertEqual(len(avail.load_credentials(d, {})[1]), 1)
            self.assertEqual(avail.load_credentials(d/'missing', {}), ({}, []))

    def test_availability_reads_bom_and_merges_repeated_mpns(self):
        avail = load(ROOT/'domains/kicad/files/tools/kicad/check_availability.py')
        with tempfile.TemporaryDirectory() as td:
            bom = Path(td)/'bom.csv'
            bom.write_text('Reference,Value,MPN,Qty\nU1,6502,W65C02S6TPG-14,1\nC1,0.1u,~,3\n'
                           'U4,74HC00,SN74HC00N,1\nU9,74HC00,sn74hc00n,2\n')
            self.assertEqual(avail.read_bom(bom), [('W65C02S6TPG-14', 1), ('SN74HC00N', 3)])
            bom.write_text('Reference,Value\nU1,6502\n')
            with self.assertRaises(ValueError):
                avail.read_bom(bom)

    def test_availability_parses_digikey_and_mouser(self):
        avail = load(ROOT/'domains/kicad/files/tools/kicad/check_availability.py')
        prod = {'ManufacturerProductNumber': 'SN74HC00N', 'Manufacturer': {'Name': 'Texas Instruments'},
                'QuantityAvailable': 10366, 'ProductStatus': {'Status': 'Active'}, 'DatasheetUrl': 'ds',
                'ProductUrl': 'url', 'ProductVariations': [
                    {'DigiKeyProductNumber': 'reel', 'MinimumOrderQuantity': 2000,
                     'QuantityAvailableforPackageType': 9000, 'StandardPricing': [{'BreakQuantity': 2000, 'UnitPrice': 0.2}]},
                    {'DigiKeyProductNumber': '296-1563-5-ND', 'MinimumOrderQuantity': 1, 'PackageType': {'Name': 'Tube'},
                     'QuantityAvailableforPackageType': 1366,
                     'StandardPricing': [{'BreakQuantity': 1, 'UnitPrice': 0.78}, {'BreakQuantity': 10, 'UnitPrice': 0.6}]}]}
        row = avail.parse_digikey({'ExactMatches': [prod], 'Products': [prod]}, 'sn74hc00n', 12)
        self.assertEqual((row['verdict'], row['distributor_pn'], row['unit_price_usd'], row['price_break_qty']),
                         ('OK', '296-1563-5-ND', 0.6, 10))
        self.assertNotIn('share', row['note'])
        self.assertEqual(avail.parse_digikey({'Products': [prod]}, 'SN74HC00N', 2000)['verdict'], 'OK')
        self.assertEqual(avail.parse_digikey({'Products': [prod]}, 'SN74HC00N', 20000)['verdict'], 'LOW_STOCK')
        obsolete = dict(prod, ProductStatus={'Status': 'Obsolete'})
        self.assertEqual(avail.parse_digikey({'Products': [obsolete]}, 'SN74HC00N', 1)['verdict'], 'NOT_ACTIVE')
        self.assertEqual(avail.parse_digikey({'Products': []}, 'SN74HC00N', 1)['verdict'], 'NOT_FOUND')

        part = {'ManufacturerPartNumber': 'W65C02S6TPG-14', 'Manufacturer': 'Western Design Center (WDC)',
                'MouserPartNumber': '955-W65C02S6TPG-14', 'Availability': '750 In Stock', 'AvailabilityInStock': '750',
                'LifecycleStatus': None, 'Min': '1',
                'PriceBreaks': [{'Quantity': 1, 'Price': '$11.04'}, {'Quantity': 25, 'Price': '$9.50'}]}
        row = avail.parse_mouser({'Errors': [], 'SearchResults': {'Parts': [part]}}, 'W65C02S6TPG-14', 1)
        self.assertEqual((row['verdict'], row['stock'], row['lifecycle'], row['unit_price_usd']), ('OK', 750, 'Active', 11.04))
        nrnd = dict(part, LifecycleStatus='Not Recommended for New Designs')
        self.assertEqual(avail.parse_mouser({'SearchResults': {'Parts': [nrnd]}}, 'W65C02S6TPG-14', 1)['verdict'], 'NOT_ACTIVE')
        gone = dict(part, AvailabilityInStock=None, Availability='On Order')
        self.assertEqual(avail.parse_mouser({'SearchResults': {'Parts': [gone]}}, 'W65C02S6TPG-14', 1)['verdict'], 'OUT_OF_STOCK')
        with self.assertRaises(LookupError):
            avail.parse_mouser({'Errors': [{'Message': 'Invalid key'}]}, 'X', 1)

    def test_availability_parses_feeder(self):
        avail = load(ROOT/'domains/kicad/files/tools/kicad/check_availability.py')
        prod = {'PartId': 5, 'ManufacturerProductNumber': 'RC0805FR-0710KL', 'Manufacturer': 'Yageo',
                'QuantityOnHand': 50, 'QuantityReserved': 4, 'QuantityAvailable': 46, 'UnitPrice': 0.05,
                'Location': {'Path': 'Cabinet 1 › Bin A-01', 'Section': 'Front'},
                'ProductUrl': 'https://feeder.example/parts/5'}
        data = {'Results': [{'PartNumber': 'rc0805fr-0710kl', 'Products': [prod]}]}
        row = avail.parse_feeder(data, 'rc0805fr-0710kl', 40)
        self.assertEqual((row['verdict'], row['stock'], row['distributor'], row['distributor_pn'], row['unit_price_usd'],
                          row['lifecycle'], row['product_url']),
                         ('OK', 46, 'Feeder', 'part 5', 0.05, 'on hand', 'https://feeder.example/parts/5'))
        self.assertIn('Cabinet 1 › Bin A-01 (Front): 46', row['note'])
        self.assertIn('4 more reserved', row['note'])
        self.assertEqual(avail.parse_feeder(data, 'X', 47)['verdict'], 'LOW_STOCK')
        # Stored in two places: the available quantities add up; a part not put away has no location.
        loose = dict(prod, PartId=9, QuantityReserved=0, QuantityAvailable=10, Location=None)
        two = avail.parse_feeder({'Results': [{'Products': [prod, loose]}]}, 'X', 56)
        self.assertEqual((two['verdict'], two['stock'], two['distributor_pn']), ('OK', 56, 'part 5, part 9'))
        self.assertIn('not put away: 10', two['note'])
        none_left = dict(prod, QuantityReserved=50, QuantityAvailable=0)
        self.assertEqual(avail.parse_feeder({'Results': [{'Products': [none_left]}]}, 'X', 1)['verdict'], 'OUT_OF_STOCK')
        self.assertEqual(avail.parse_feeder({'Results': [{'Products': []}]}, 'X', 1)['verdict'], 'NOT_FOUND')
        self.assertEqual(avail.parse_feeder({}, 'X', 1)['verdict'], 'NOT_FOUND')

    def test_availability_feeder_url_must_be_https_except_on_this_computer(self):
        avail = load(ROOT/'domains/kicad/files/tools/kicad/check_availability.py')
        self.assertEqual(avail.feeder_base_url('https://feeder.example/'), 'https://feeder.example')
        self.assertEqual(avail.feeder_base_url('http://localhost:8085'), 'http://localhost:8085')
        self.assertEqual(avail.feeder_base_url('http://127.0.0.1:8085/'), 'http://127.0.0.1:8085')
        for bad in ('http://feeder.example', 'feeder.example', 'ftp://feeder.example', 'https://'):
            with self.assertRaises(ValueError):
                avail.feeder_base_url(bad)
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/'feeder.env').write_text('FEEDER_URL=https://feeder.example\nFEEDER_API_KEY=feeder_fake\n')
            (Path(td)/'feeder.env').chmod(0o600)
            creds, _ = avail.load_credentials(Path(td), {})
            self.assertEqual(creds, {'FEEDER_URL': 'https://feeder.example', 'FEEDER_API_KEY': 'feeder_fake'})
            saved = {k: os.environ.pop(k) for k in avail.SECRET_KEYS if k in os.environ}
            try:
                (Path(td)/'feeder.env').write_text('FEEDER_URL=http://feeder.example\nFEEDER_API_KEY=feeder_fake\n')
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(avail.main(['X', '--config-dir', td, '--output', td]), 2)
                self.assertIn('https://', err.getvalue())
                self.assertNotIn('feeder_fake', err.getvalue())
            finally:
                os.environ.update(saved)

    def test_availability_needs_credentials_and_passes_only_with_an_ok_distributor(self):
        avail = load(ROOT/'domains/kicad/files/tools/kicad/check_availability.py')
        saved = {k: os.environ.pop(k) for k in avail.SECRET_KEYS if k in os.environ}
        try:
            with tempfile.TemporaryDirectory() as td, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(avail.main(['X', '--config-dir', td, '--output', td]), 2)
        finally:
            os.environ.update(saved)

        class Fake:
            def __init__(self, name, verdict):
                self.name, self.verdict = name, verdict
            def lookup(self, mpn, needed):
                return avail.result(mpn, needed, self.name, verdict=self.verdict)
        rows, failures = avail.check([('A', 2)], [Fake('Digi-Key', 'NOT_FOUND'), Fake('Mouser', 'OK')], 3, 't')
        self.assertEqual((failures, [r['needed_qty'] for r in rows]), ([], [6, 6]))
        _, failures = avail.check([('A', 1)], [Fake('Digi-Key', 'LOW_STOCK')], 1, 't')
        self.assertEqual(failures, ['A'])
        _, failures = avail.check([('A', 1)], [Fake('Feeder', 'OK'), Fake('Digi-Key', 'NOT_ACTIVE')], 1, 't')
        self.assertEqual(failures, [])

    def test_availability_search_parses_both_distributors(self):
        avail = load(ROOT/'domains/kicad/files/tools/kicad/check_availability.py')
        prod = {'ManufacturerProductNumber': 'LDD-700L', 'Manufacturer': {'Name': 'MEAN WELL USA Inc.'},
                'QuantityAvailable': 133, 'ProductStatus': {'Status': 'Active'}, 'DatasheetUrl': 'ds', 'ProductUrl': 'url',
                'Description': {'ProductDescription': 'LED DRIVER CC DC/DC', 'DetailedDescription': 'LED Driver IC 700mA'},
                'Category': {'Name': 'Power Supplies', 'ChildCategories': [{'Name': 'LED Drivers', 'ChildCategories': []}]},
                'Parameters': [{'ParameterText': 'Current - Output', 'ValueText': '700mA'},
                               {'ParameterText': 'Dimming', 'ValueText': 'PWM'}],
                'ProductVariations': [{'DigiKeyProductNumber': '1866-LDD-700L-ND', 'MinimumOrderQuantity': 1,
                                       'QuantityAvailableforPackageType': 133,
                                       'StandardPricing': [{'BreakQuantity': 1, 'UnitPrice': 9.5}]}]}
        rows = avail.parse_digikey_search({'ExactMatches': [prod], 'Products': [prod]})
        self.assertEqual(len(rows), 1)  # ExactMatches repeats Products
        row = rows[0]
        self.assertEqual((row['distributor'], row['mpn'], row['category'], row['stock'], row['active'],
                          row['distributor_pn'], row['unit_price_usd'], row['description']),
                         ('Digi-Key', 'LDD-700L', 'LED Drivers', 133, True, '1866-LDD-700L-ND', 9.5, 'LED Driver IC 700mA'))
        self.assertEqual(row['parameters'], 'Current - Output: 700mA; Dimming: PWM')
        self.assertEqual(set(row), set(avail.SEARCH_FIELDS))

        part = {'ManufacturerPartNumber': 'IRM-03-3.3', 'Manufacturer': 'MEAN WELL', 'MouserPartNumber': '709-IRM03-3.3',
                'Description': 'Switching Power Supplies 3W 3.3V', 'Category': 'Switching Power Supplies',
                'AvailabilityInStock': '1396', 'LifecycleStatus': None, 'Min': '1',
                'PriceBreaks': [{'Quantity': 1, 'Price': '$7.20'}],
                'ProductAttributes': [{'AttributeName': 'Output Voltage', 'AttributeValue': '3.3 V'}]}
        row = avail.parse_mouser_search({'Errors': [], 'SearchResults': {'Parts': [part]}})[0]
        self.assertEqual((row['distributor'], row['stock'], row['lifecycle'], row['active'], row['unit_price_usd'],
                          row['parameters']),
                         ('Mouser', 1396, 'Active', True, 7.2, 'Output Voltage: 3.3 V'))
        self.assertEqual(avail.parse_mouser_search({'SearchResults': {'Parts': []}}), [])
        with self.assertRaises(LookupError):
            avail.parse_mouser_search({'Errors': [{'Message': 'Invalid key'}]})

    def test_availability_search_filters_sorts_and_reports_errors(self):
        avail = load(ROOT/'domains/kicad/files/tools/kicad/check_availability.py')

        def row(mpn, stock, active, parameters=''):
            return avail.search_result('X', mpn, {'stock': stock, 'active': active, 'lifecycle': 'Active'},
                                       description='LED driver', category='LED Drivers', parameters=parameters)

        class Fake:
            def __init__(self, name, rows=None, error=None):
                self.name, self.rows, self.error, self.calls = name, rows or [], error, []
            def search(self, keywords, limit, in_stock):
                self.calls.append((keywords, limit, in_stock))
                if self.error:
                    raise LookupError(self.error)
                return [dict(r) for r in self.rows]

        dk = Fake('Digi-Key', [row('A', 5, True, 'Dimming: 0-10V'), row('B', 0, True, 'Dimming: PWM'),
                               row('C', 900, False, 'Dimming: 0-10V')])
        mouser = Fake('Mouser', error='HTTP 403 Forbidden')
        rows, errors = avail.run_search('led driver', [dk, mouser], 10, 't')
        self.assertEqual(([r['mpn'] for r in rows], errors), (['C', 'A', 'B'], ['Mouser: HTTP 403 Forbidden']))
        self.assertEqual(rows[0]['searched_at_utc'], 't')
        self.assertEqual(dk.calls, [('led driver', 10, False)])
        rows, _ = avail.run_search('led driver', [dk], 10, 't', in_stock=True, active=True)
        self.assertEqual([r['mpn'] for r in rows], ['A'])
        rows, _ = avail.run_search('led driver', [dk], 10, 't', require=['0-10v', 'led'])
        self.assertEqual([r['mpn'] for r in rows], ['C', 'A'])
        rows, _ = avail.run_search('led driver', [dk], 10, 't', require=['dali'])
        self.assertEqual(rows, [])

    def test_availability_search_command_line_rules(self):
        avail = load(ROOT/'domains/kicad/files/tools/kicad/check_availability.py')
        with tempfile.TemporaryDirectory() as td, contextlib.redirect_stderr(io.StringIO()):
            for argv in (['X', '--search', 'led driver'], ['--search', '  '], ['--search', 'x', '--limit', '0'],
                         ['--search', 'x', '--limit', '51'], ['X', '--in-stock'], ['X', '--require', 'pwm'], []):
                with self.assertRaises(SystemExit) as cm:
                    avail.main(argv + ['--config-dir', td, '--output', td])
                self.assertEqual(cm.exception.code, 2, argv)
        saved = {k: os.environ.pop(k) for k in avail.SECRET_KEYS if k in os.environ}
        try:
            with tempfile.TemporaryDirectory() as td:
                (Path(td)/'feeder.env').write_text('FEEDER_URL=https://feeder.example\nFEEDER_API_KEY=feeder_fake\n')
                (Path(td)/'feeder.env').chmod(0o600)
                # Feeder alone cannot search, so a search with only Feeder configured is a configuration error.
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(avail.main(['--search', 'led driver', '--config-dir', td, '--output', td]), 2)
                self.assertIn('not used for --search', err.getvalue())
                self.assertNotIn('feeder_fake', err.getvalue())
        finally:
            os.environ.update(saved)

    def test_domain_scripts_compile(self):
        for script in (ROOT/'domains').rglob('*.py'):
            compile(script.read_text(), str(script), 'exec')

if __name__=='__main__': unittest.main()
