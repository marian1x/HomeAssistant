"""Synthetic energy/weather fixture. This never reads or writes production HA."""
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import runpy
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import energy
schema=runpy.run_path(str(ROOT/'ha/custom_components/home_energy_policy/schema.py'))
pricing=runpy.run_path(str(ROOT/'ha/custom_components/home_energy_policy/pricing.py'))
c=schema['DEFAULTS']
tz=ZoneInfo('Europe/Bucharest')
now=datetime.now(tz).replace(hour=12,minute=0,second=0,microsecond=0)
start=now.replace(day=1,hour=0)
training_start=start-timedelta(days=20)
raw={e:[] for e in list(energy.ENERGY.values())+list(energy.WEATHER.values())}
stamp=training_start
while stamp+timedelta(hours=1)<=now:
    hour=stamp.hour
    solar=max(0,math.sin((hour-6)/12*math.pi))*(3+stamp.day%2*2)
    values={'import_kwh':.5 if hour<8 or hour>17 else .1,'export_kwh':max(0,solar-1.3),
            'load_kwh':.5+(1.8 if hour in (7,20) else 0),'solar_kwh':solar,
            'boiler_kwh':1.8 if hour in (7,20) else 0,'temperature':10+4*math.sin(hour/24*math.pi*2), 'clouds':40}
    for key,value in values.items():
        raw[(energy.ENERGY|energy.WEATHER)[key]].append({'start':stamp.timestamp()*1000,'end':(stamp+timedelta(hours=1)).timestamp()*1000,
            'change' if key in energy.ENERGY else 'mean':value})
    stamp+=timedelta(hours=1)
tariffs=pricing['initial'](c)
report=energy.report(raw,start,now,tariffs)
training=energy.report(raw,training_start,now,tariffs)
solar=[];weather=[]
for day in range(6):
    begin=now.replace(hour=0)+timedelta(days=day)
    hours=[]
    for h in range(24):
        t=(begin+timedelta(hours=h)).timestamp()*1000
        pv=max(0,math.sin((h-6)/12*math.pi))*(1.3+day*.3)
        hours.append({'time':t,'energy_kwh':pv})
        weather.append({'time':t,'temperature':7+day,'clouds':85-day*10,'code':3})
    solar.append({'date':begin.date().isoformat(),'energy_kwh':sum(h['energy_kwh'] for h in hours),'hours':hours})
feed={'timezone':'Europe/Bucharest','now':now.isoformat(),'weather':{'hours':weather,'fetched_at':now.isoformat(),'error':''},'solar':solar,
      'battery':{'soc':55,'capacity_kwh':16,'reserve_soc':20,'charge_kw':7,'discharge_kw':7},
      'today':{'load_kwh':6,'solar_kwh':2,'import_kwh':1,'export_kwh':0}}
out={'report':report,'month':report,'outlook':energy.forecast(feed,training,c,tariffs),
     'pricing':{'revision':1,'config':{k:v for k,v in c.items() if k.startswith('energy_')},'active':tariffs[-1],'history':tariffs},'timezone':'Europe/Bucharest'}
(ROOT/'tests/fixtures/finance.json').write_text(json.dumps(out),encoding='utf-8')
