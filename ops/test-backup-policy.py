"""Render the backup and pause policy with isolated HA states; no real services."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
import yaml


async def main():
    with tempfile.TemporaryDirectory() as root:
        hass=HomeAssistant(root)
        packages=Path('/config/packages')
        backup=yaml.safe_load((packages/'backup_strategy.yaml').read_text())
        global_policy=yaml.safe_load((packages/'global_automation_killswitch.yaml').read_text())
        scheduled=backup['automation'][0]
        assert [t['at'] for t in scheduled['triggers']]==['07:00:00','19:00:00']
        assert scheduled['initial_state'] is True
        assert scheduled['actions'][0]['data']['homeassistant_exclude_database'] is False
        variables=global_policy['automation'][0]['action'][0]['variables']
        ids=['automation.ha_global_automation_killswitch_controller','automation.ha_full_backup_morning_and_evening',
             'automation.ha_backup_integrity_monitor','automation.tesla_test','automation.climate_test']
        for entity in ids:hass.states.async_set(entity,'on')
        controlled=Template(variables['controlled_automations'],hass).async_render(variables=variables)
        assert set(controlled)=={'automation.tesla_test','automation.climate_test'}
        monitor=backup['automation'][1]
        text=next(a['variables']['uploaded_full'] for a in monitor['actions'] if 'variables' in a)
        now=datetime.now(timezone.utc)
        recent=(now-timedelta(hours=4)).isoformat()
        old=(now-timedelta(hours=20)).isoformat()
        rows=[{'name':'HA full recent','date':recent,'state':'Backed Up'},
              {'name':'HA full pending','date':now.isoformat(),'state':'Uploading'},
              {'name':'Upgrade','date':now.isoformat(),'state':'Backed Up'}]
        hass.states.async_set('sensor.backup_state','backed_up',{'backups':rows})
        stamp=Template(text,hass).async_render()
        assert abs(float(stamp)-datetime.fromisoformat(recent).timestamp())<1
        rows[0]['date']=old
        hass.states.async_set('sensor.backup_state','backed_up',{'backups':rows})
        assert now.timestamp()-float(Template(text,hass).async_render())>64800
        print('PASS: two daily full backups including DB; pause excludes only backup maintenance; alert ignores partial/unuploaded backups; no services called.')


asyncio.run(main())
