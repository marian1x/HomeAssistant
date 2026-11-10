"""Synthetic isolated browser fixture, generated from the same bounded schema."""
import json
from pathlib import Path
import runpy
root = Path(__file__).resolve().parents[1]
schema = runpy.run_path(str(root/'ha/custom_components/home_energy_policy/schema.py'))
fixture = {'revision':1, 'config':schema['DEFAULTS'] | {'enabled':True}, 'schema':schema['FIELDS'],
           'status':{'phase':'Confort', 'reason':'Surplus masurat dupa incarcarea bateriei', 'season':'Winter', 'power_valid':True,
                     'solar_budget_kw':0,'battery_soc':72,'outside_c':1,'forecast_remaining_kwh':2.5,
                     'tesla_quota':{'polling_protected':True,'reads_day':1,'reads_month':15,'commands_day':0,'commands_month':5},
                     'devices':{'boiler':{'mode':'normal','temperature':47,'reason':'Temperatura de baza'},
                                'whirlpool':{'mode':'manual','manual_until':9999999999,'reason':'Interventie manuala'},
                                'tesla':{'mode':'unavailable','reason':'Reinrolare necesara'},'tcl':{'mode':'unavailable','reason':'Neintegrat'}}}}
(root/'tests/fixtures/policy.json').write_text(json.dumps(fixture),encoding='utf-8')
