from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import importlib.util
from pathlib import Path
import pytest
from server import energy
from server.policy import Rejected

TZ = ZoneInfo('Europe/Bucharest')
ROOT = Path(__file__).resolve().parents[1]/'ha/custom_components/home_energy_policy'


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


schema, pricing = module('schema'), module('pricing')
CONFIG=schema.DEFAULTS
HISTORY=pricing.initial(CONFIG)


def sample(start,end,value):
    return {'start':start.timestamp()*1000,'end':end.timestamp()*1000,'change':value}


def test_cash_balance_and_units_are_kwh_not_kw():
    start=datetime(2026,11,9,tzinfo=TZ);end=start+timedelta(days=1)
    data={energy.ENERGY['import_kwh']:[sample(start,end,2)],energy.ENERGY['export_kwh']:[sample(start,end,10)]}
    r=energy.report(data,start,end,HISTORY)
    assert r['totals']['import_cost_ron']==pytest.approx(2.22)
    assert r['totals']['export_income_ron']==pytest.approx(4.5)
    assert r['totals']['balance_ron']==pytest.approx(2.28)
    assert r['complete_days']==1


def test_tariff_change_does_not_reprice_past_days():
    newer=pricing.update(HISTORY,CONFIG|{'energy_import_price':2,'energy_tariff_from':'2026-11-10'})
    assert pricing.active(newer,'2026-11-09')['import_price']==1.11
    assert pricing.active(newer,'2026-11-10')['import_price']==2
    assert len(pricing.update(newer,CONFIG|{'energy_import_price':3,'energy_tariff_from':'2026-11-10'}))==len(newer)


def test_missing_days_are_not_zero_and_negative_deltas_are_rejected():
    a=datetime(2026,11,9,tzinfo=TZ);b=a+timedelta(days=2)
    r=energy.report({energy.ENERGY['import_kwh']:[sample(a,a+timedelta(hours=1),-9)]},a,b,HISTORY)
    assert r['totals']['balance_ron'] is None and r['totals']['import_kwh'] is None
    assert all(d['import_kwh'] is None for d in r['days'])
    assert r['days'][0]['invalid_samples']==1


@pytest.mark.parametrize('day,hours',[('2026-03-29',23),('2026-10-25',25)])
def test_local_days_handle_dst(day,hours):
    start,end=energy.boundaries(day,day,TZ,datetime(2026,12,1,tzinfo=TZ))
    assert (end.timestamp()-start.timestamp())/3600==hours
    rows=[];stamp=start.astimezone(timezone.utc)
    while stamp<end:
        rows.append(sample(stamp,stamp+timedelta(hours=1),1));stamp+=timedelta(hours=1)
    r=energy.report({energy.ENERGY['import_kwh']:rows,energy.ENERGY['export_kwh']:rows},start,end,HISTORY)
    assert r['complete_days']==1 and r['totals']['import_kwh']==hours


@pytest.mark.parametrize('start,end',[('2026-11-10','2026-11-09'),('2026-11-9','2026-11-09'),('1999-01-01','2026-11-09'),('2020-01-01','2026-11-09'),('2026-11-09','2026-11-11')])
def test_bounded_date_queries(start,end):
    with pytest.raises(Rejected):energy.boundaries(start,end,TZ,datetime(2026,11,9,12,tzinfo=TZ))


def test_short_term_samples_are_added_once_and_grouped_into_hours():
    a=datetime(2026,11,9,tzinfo=TZ)
    data={energy.ENERGY['import_kwh']:[sample(a,a+timedelta(minutes=5),.1),sample(a+timedelta(minutes=5),a+timedelta(minutes=10),.2)]}
    r=energy.report(data,a,a+timedelta(hours=1),HISTORY)
    assert len(r['hours'])==1 and r['hours'][0]['import_kwh']==pytest.approx(.3)


def test_historical_weather_has_no_unbounded_carry_across_data_gaps():
    a=datetime(2026,11,9,tzinfo=TZ);end=a+timedelta(days=1)
    one=[{'last_updated':a.isoformat(),'attributes':{'temperature':20,'cloud_coverage':50}}]
    assert energy.raw_weather_days(one,TZ,a,end)=={}
    series=[{'last_updated':(a+timedelta(hours=h)).isoformat(),'attributes':{'temperature':20,'cloud_coverage':50}} for h in range(24)]
    assert energy.raw_weather_days(series,TZ,a,end)['2026-11-09']['temperature']==20


def test_current_tariff_simulation_is_separate_from_history():
    a=datetime(2026,11,9,tzinfo=TZ);end=a+timedelta(days=1)
    data={energy.ENERGY['import_kwh']:[sample(a,end,1)]}
    current={'import_price':2,'export_price':1}
    r=energy.report(data,a,end,HISTORY,'current',current)
    assert r['totals']['import_cost_ron']==2
    assert energy.report(data,a,end,HISTORY)['totals']['import_cost_ron']==1.11


def make_feed(solar=0,soc=100):
    a=datetime(2026,11,9,tzinfo=TZ)
    hours=[{'time':(a+timedelta(hours=h)).timestamp()*1000,'temperature':10,'clouds':60,'code':3} for h in range(24)]
    return {'now':a.isoformat(),'timezone':'Europe/Bucharest','weather':{'hours':hours},
            'solar':[{'date':'2026-11-09','energy_kwh':solar*24,'hours':[{'time':h['time'],'energy_kwh':solar} for h in hours]}],
            'battery':{'soc':soc,'capacity_kwh':16,'reserve_soc':20,'charge_kw':7,'discharge_kw':7},
            'today':{'import_kwh':0,'export_kwh':0,'load_kwh':0,'solar_kwh':0}}


def test_battery_prediction_respects_twenty_percent_and_never_grid_charges():
    r=energy.forecast(make_feed(),{'days':[],'hours':[]},CONFIG,HISTORY)
    assert r['days'][0]['battery_end_soc']==pytest.approx(20)
    assert r['days'][0]['import_kwh']>0 and r['days'][0]['export_kwh']==0
    assert r['assumptions']['grid_battery_charging'] is False


def test_solar_prediction_charges_battery_before_export():
    r=energy.forecast(make_feed(solar=4,soc=20),{'days':[],'hours':[]},CONFIG,HISTORY)
    assert r['days'][0]['battery_end_soc']==pytest.approx(100)
    assert r['days'][0]['export_kwh']>0


def test_missing_forecast_is_not_treated_as_zero_production():
    feed=make_feed();feed['solar'][0]['energy_kwh']=None;feed['solar'][0]['hours']=[]
    r=energy.forecast(feed,{'days':[],'hours':[]},CONFIG,HISTORY)
    assert r['days'][0]['balance_ron'] is None


def test_manual_thermal_sensitivity_works_before_historical_weather_exists():
    feed=make_feed()
    next_day={**feed['solar'][0], 'date':'2026-11-10',
              'hours':[{**h,'time':h['time']+86400000} for h in feed['solar'][0]['hours']]}
    feed['solar'].append(next_day)
    feed['weather']['hours'] += [{**h,'time':h['time']+86400000,'temperature':0} for h in list(feed['weather']['hours'])]
    history={'days':[{'date':'2026-11-08','complete':True,'load_complete':True,'load_kwh':20}], 'hours':[]}
    result=energy.forecast(feed,history,CONFIG,HISTORY)
    assert result['assumptions']['temperature_reference_assumed'] is True
    assert result['days'][1]['load_kwh'] > result['days'][0]['load_kwh']


@pytest.mark.parametrize('values',[{'energy_import_price':float('nan')},{'energy_export_price':-1},{'energy_tariff_from':'2026-02-30'},{'energy_tariff_from':'x'},{'planning_battery_efficiency':110}])
def test_tariff_and_planning_validation(values):
    with pytest.raises(ValueError):schema.validate(values)
