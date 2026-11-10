"""Live accounting check; optional explicit Energy price linking. No actuators."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import aiohttp

sys.path.insert(0,'/config/control_center/finance_checks')
from server import energy


async def main():
    token=os.environ['CONTROL_TOKEN']
    async with aiohttp.ClientSession(headers={'Authorization':'Bearer '+token}) as session:
        async def api(method,path,data=None,params=None):
            async with session.request(method,'http://supervisor/core/api/'+path,json=data,params=params) as response:
                if response.status>=400:raise RuntimeError('HA API status '+str(response.status))
                return await response.json()
        async with session.ws_connect('http://supervisor/core/websocket') as socket:
            if (await socket.receive_json())['type']=='auth_required':
                await socket.send_json({'type':'auth','access_token':token})
                assert (await socket.receive_json())['type']=='auth_ok'
            class Peer:
                sequence=0
                async def call(self,data):
                    self.sequence+=1
                    await socket.send_json({'id':self.sequence,**data})
                    while True:
                        packet=await socket.receive_json()
                        if packet.get('id')==self.sequence:
                            if not packet.get('success'):raise RuntimeError('Native action failed: '+data['type'])
                            return packet['result']
            peer=Peer()
            policy=await peer.call({'type':'home_energy_policy/get'})
            if '--link-energy-prices' in sys.argv:
                prefs=await peer.call({'type':'energy/get_prefs'})
                backup=Path('/config/control_center/backups/energy-costs-20261109-092017/energy-prefs-before-price-link.json')
                if not backup.exists():
                    backup.write_text(json.dumps(prefs),encoding='utf-8')
                    backup.chmod(0o600)
                for source in prefs['energy_sources']:
                    if source.get('type')=='grid' and source.get('stat_energy_from')=='sensor.deye_total_energy_import':
                        source.update(entity_energy_price='sensor.home_energy_import_price',
                                      entity_energy_price_export='sensor.home_energy_export_price')
                        source.pop('number_energy_price',None)
                        source.pop('number_energy_price_export',None)
                await peer.call({'type':'energy/save_prefs',**prefs})
                check=await peer.call({'type':'energy/get_prefs'})
                assert any(s.get('entity_energy_price')=='sensor.home_energy_import_price' and
                           s.get('entity_energy_price_export')=='sensor.home_energy_export_price' for s in check['energy_sources'])
            feed=await peer.call({'type':'home_energy_policy/outlook'})
            tz=ZoneInfo(feed['timezone']);now=datetime.now(tz)
            begin=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
            raw=await energy.read_statistics(peer,begin,now,'hour')
            report=energy.report(raw,begin,now,policy['tariffs'])
            history_start=begin-timedelta(days=28)
            weather=await api('GET','history/period/'+history_start.isoformat(),params={'filter_entity_id':'weather.forecast_home','end_time':now.isoformat()})
            actual=energy.raw_weather_days(weather[0] if weather else [],tz,begin,now)
            for row in report['days']:
                if row['date'] in actual:
                    for key,value in actual[row['date']].items():
                        if row[key] is None:row[key]=value
            predicted=energy.forecast(feed,report,policy['config'],policy['tariffs'])
            entries=await peer.call({'type':'config_entries/get'})
            tesla=[{'state':e['state'],'polling_disabled':e.get('pref_disable_polling')} for e in entries if e['domain']=='tesla_custom']
            flow=await api('POST','config/config_entries/flow',{'handler':'tcl_home_unofficial','show_advanced_options':False})
            form_ok=flow.get('type')=='form' and flow.get('step_id')=='user'
            if flow.get('flow_id'):
                await api('DELETE','config/config_entries/flow/'+flow['flow_id'])
            print(json.dumps({'month':{'days':len(report['days']),'complete':report['complete_days'],'totals':report['totals'],'data_through':report['data_through']},
                              'forecast_days':len(predicted['days']),'forecast':[{k:r.get(k) for k in ('date','solar_kwh','load_kwh','import_kwh','balance_ron','battery_end_soc','confidence')} for r in predicted['days']],
                              'weather_sample_days':predicted['weather_sample_days'],'tariff':policy['active_tariff'],
                              'tcl_configuration_form_available':form_ok,'tesla':tesla,'actuator_commands':0}))


asyncio.run(main())
