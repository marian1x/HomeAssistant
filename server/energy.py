"""Read-only energy accounting from Recorder deltas; never poll devices."""
from collections import defaultdict
from datetime import date, datetime, time as clock, timedelta, timezone
import math
from decimal import Decimal
from statistics import median, linear_regression
from zoneinfo import ZoneInfo

from .policy import Rejected

ENERGY = {'import_kwh':'sensor.deye_total_energy_import', 'export_kwh':'sensor.deye_total_energy_export',
          'load_kwh':'sensor.deye_total_load_consumption', 'solar_kwh':'sensor.deye_productie_solara_total',
          'boiler_kwh':'sensor.ariston_boiler_energy_total'}
WEATHER = {'temperature':'sensor.home_energy_outdoor_temperature', 'clouds':'sensor.home_energy_cloud_coverage'}


def finite(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def timestamp(value):
    if isinstance(value, (int,float)):
        return float(value)/1000
    return datetime.fromisoformat(value).timestamp()


def boundaries(start, end, tz, now):
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first.isoformat() != start or last.isoformat() != end or first > last or (last-first).days > 1826 or first.year < 2000 or last > now.astimezone(tz).date():
            raise ValueError
        begin = datetime.combine(first, clock(), tz)
        finish = min(datetime.combine(last+timedelta(days=1), clock(), tz), now)
        return begin, finish
    except (ValueError, TypeError):
        raise Rejected('Alege un interval valid, de maximum 5 ani, fara zile viitoare.', 422)


def tariff(history, day):
    rows = [r for r in history if r['from'] <= day]
    if not rows:
        raise Rejected('Nu exista tarif pentru acest interval.', 409)
    return max(rows, key=lambda r:r['from'])


def priced(kwh, price):
    return float(Decimal(str(kwh))*Decimal(str(price)))


async def read_statistics(peer, start, end, period):
    async def call(a, b, interval):
        return await peer.call({'type':'recorder/statistics_during_period', 'start_time':a.isoformat(), 'end_time':b.isoformat(),
            'statistic_ids':list(ENERGY.values())+list(WEATHER.values()), 'period':interval,
            'types':['change','mean'], 'units':{'energy':'kWh','temperature':'°C'}})
    data = await call(start, end, period)
    now = datetime.now(timezone.utc)
    if end >= now-timedelta(minutes=10):
        # Replace today's coarse row, then append only short-term buckets after the
        # last complete hour. This never extends a last value into future hours.
        today = datetime.combine(end.astimezone(start.tzinfo).date(), clock(), start.tzinfo)
        if period == 'day':
            for entity in data:
                data[entity] = [r for r in data[entity] if timestamp(r['start']) < today.timestamp()]
            recent = await call(today, end, 'hour')
            for entity, rows in recent.items(): data.setdefault(entity, []).extend(rows)
        ends = [timestamp(r['end']) for entity in (ENERGY['import_kwh'],ENERGY['export_kwh']) for r in data.get(entity,[]) if timestamp(r['end']) <= end.timestamp()]
        cutoff = max(ends, default=max(start.timestamp(), end.timestamp()-3600))
        cutoff = max(cutoff, end.timestamp()-7200, start.timestamp())
        tail = await call(datetime.fromtimestamp(cutoff,timezone.utc), end, '5minute')
        for entity, rows in tail.items():
            prior_end = max((timestamp(r['end']) for r in data.get(entity, [])), default=cutoff)
            data.setdefault(entity, []).extend(r for r in rows if timestamp(r['start']) >= prior_end and timestamp(r['end']) <= end.timestamp())
    return data


def report(data, start, end, history, mode='historical', current=None):
    tz = start.tzinfo
    days, hours = {}, {}
    day = start.date()
    while day <= end.astimezone(tz).date():
        if datetime.combine(day, clock(), tz) >= end: break
        key = day.isoformat()
        days[key] = {'date':key, **{k:None for k in ENERGY}, 'temperature':None,'clouds':None,
                     'coverage':{}, 'import_cost_ron':None,'export_income_ron':None,'balance_ron':None, 'invalid_samples':0}
        day += timedelta(days=1)
    last_data = None
    reverse = {entity:key for key,entity in (ENERGY|WEATHER).items()}
    weights = defaultdict(lambda:[0.,0.])
    for entity, samples in data.items():
        key = reverse.get(entity)
        if not key: continue
        for sample in samples:
            stamp, stop = timestamp(sample['start']), timestamp(sample['end'])
            if not start.timestamp() <= stamp < end.timestamp() or stop > end.timestamp()+1:
                continue
            day = datetime.fromtimestamp(stamp,tz).date().isoformat()
            if day not in days: continue
            value = finite(sample.get('change' if key in ENERGY else 'mean'))
            if value is None: continue
            row = days[day]
            duration = stop-stamp
            if key in ENERGY:
                if value < -1e-5:
                    row['invalid_samples'] += 1
                    continue
                value = max(0,value)
                row[key] = (row[key] or 0)+value
                row['coverage'][key] = row['coverage'].get(key,0)+duration
                last_data = max(last_data or stop,stop)
            else:
                weights[day,key][0] += value*duration
                weights[day,key][1] += duration
            # A daily sample is not an hourly load profile.
            if duration <= 3600:
                hour_stamp = stamp-stamp%3600
                h = hours.setdefault(hour_stamp, {'time':hour_stamp*1000,'end':stop*1000,'date':day,'_weather':{}})
                h['end'] = max(h['end'],stop*1000)
                if key in ENERGY: h[key] = (h.get(key) or 0)+value
                else:
                    v = h['_weather'].setdefault(key,[0,0])
                    v[0] += value*duration; v[1] += duration
    for row in days.values():
        for key in WEATHER:
            total, duration = weights[row['date'],key]
            if duration: row[key] = total/duration
        rate = current if mode == 'current' else tariff(history,row['date'])
        row.update(import_price=rate['import_price'], export_price=rate['export_price'], tariff_assumed=rate.get('assumed',False))
        if row['import_kwh'] is not None: row['import_cost_ron'] = priced(row['import_kwh'],rate['import_price'])
        if row['export_kwh'] is not None: row['export_income_ron'] = priced(row['export_kwh'],rate['export_price'])
        if row['import_cost_ron'] is not None and row['export_income_ron'] is not None:
            row['balance_ron'] = row['export_income_ron']-row['import_cost_ron']
        row['savings_ron'] = priced(row['load_kwh'],rate['import_price'])+row['balance_ron'] if row['load_kwh'] is not None and row['balance_ron'] is not None else None
        begin = datetime.combine(date.fromisoformat(row['date']),clock(),tz)
        finish = min(begin+timedelta(days=1),end)
        expected = finish.timestamp()-begin.timestamp()
        row['coverage_pct'] = min(100,100*min(row['coverage'].get('import_kwh',0),row['coverage'].get('export_kwh',0))/expected) if expected else 0
        row['complete'] = row['coverage_pct'] >= 95 and not row['invalid_samples']
        row['load_complete'] = expected > 0 and row['coverage'].get('load_kwh',0) >= expected*.95
    rows = list(days.values())
    totals = {}
    for key in list(ENERGY)+['import_cost_ron','export_income_ron','balance_ron','savings_ron']:
        values = [r[key] for r in rows if r[key] is not None]
        totals[key] = sum(values) if values else None
    for h in hours.values():
        for k,(total,duration) in h.pop('_weather').items(): h[k] = total/duration
    return {'start':start.date().isoformat(),'end':(end-timedelta(microseconds=1)).astimezone(tz).date().isoformat(),
            'days':rows, 'hours':[hours[k] for k in sorted(hours)], 'totals':totals, 'tariff_mode':mode,
            'complete_days':sum(r['complete'] for r in rows),'total_days':len(rows),
            'data_through':datetime.fromtimestamp(last_data,timezone.utc).isoformat() if last_data else None,
            'source':'Contoare Deye; boiler estimat din rezistenta de 1.8 kW'}


def raw_weather_days(series, tz, start, end):
    events = []
    for row in series:
        try:
            stamp = datetime.fromisoformat(row.get('last_updated') or row['last_changed']).timestamp()
            attrs = row.get('attributes',{})
            temp, cloud = finite(attrs.get('temperature')), finite(attrs.get('cloud_coverage'))
            if temp is not None and attrs.get('temperature_unit') == '°F': temp = (temp-32)*5/9
            if temp is not None: events.append((stamp,temp,cloud))
        except (KeyError,TypeError,ValueError): continue
    events.sort()
    values = defaultdict(lambda:[0,0,0,0])
    for i,(stamp,temp,cloud) in enumerate(events):
        finish = min(events[i+1][0] if i+1<len(events) else end.timestamp(),stamp+7200,end.timestamp())
        stamp = max(stamp,start.timestamp())
        while stamp < finish:
            local = datetime.fromtimestamp(stamp,tz)
            boundary = datetime.combine(local.date()+timedelta(days=1),clock(),tz).timestamp()
            stop = min(boundary,finish)
            seconds = stop-stamp
            v = values[local.date().isoformat()]
            v[0] += temp*seconds; v[1] += seconds
            if cloud is not None: v[2] += cloud*seconds; v[3] += seconds
            stamp = stop
    output = {}
    for day,v in values.items():
        begin = datetime.combine(date.fromisoformat(day),clock(),tz)
        duration = (begin+timedelta(days=1)).timestamp()-begin.timestamp()
        if v[1] >= duration*.75:
            output[day] = {'temperature':v[0]/v[1], 'clouds':v[2]/v[3] if v[3] >= duration*.75 else None}
    return output


def forecast(feed, history, config, tariffs):
    tz = ZoneInfo(feed['timezone'])
    now = datetime.fromisoformat(feed['now'])
    complete = [r for r in history['days'] if r['complete'] and r.get('load_complete',True) and r['date'] < now.date().isoformat() and r['load_kwh'] is not None and r['load_kwh']>0]
    reference = median([r['load_kwh'] for r in complete]) if complete else config['planning_base_kwh']
    paired = [r for r in complete if r.get('temperature') is not None]
    ref_temp = median([r['temperature'] for r in paired]) if paired else None
    today_temperatures = [h['temperature'] for h in feed['weather'].get('hours',[])
                          if datetime.fromtimestamp(h['time']/1000,tz).date() == now.date()]
    assumed_temperature = ref_temp is None and bool(complete) and bool(today_temperatures)
    if assumed_temperature:
        ref_temp = sum(today_temperatures)/len(today_temperatures)
    heat, cool = config['planning_heat_kwh_degree'], config['planning_cool_kwh_degree']
    learned = False
    if config['planning_auto_calibration'] and len(paired) >= 14:
        for kind in ('heat','cool'):
            x = [max(0,config['planning_heat_base_c']-r['temperature']) if kind=='heat' else max(0,r['temperature']-config['planning_cool_base_c']) for r in paired]
            if max(x)-min(x) >= 3:
                regression = linear_regression(x,[r['load_kwh'] for r in paired])
                if 0 <= regression.slope <= 8:
                    if kind=='heat': heat=regression.slope
                    else: cool=regression.slope
                    learned=True
    shape = defaultdict(list)
    daily_totals = {r['date']:r['load_kwh'] for r in complete}
    local_hours = defaultdict(float)
    for h in history['hours']:
        if h.get('load_kwh') is not None and h['date'] in daily_totals:
            hour = datetime.fromtimestamp(h['time']/1000,tz).hour
            local_hours[h['date'],hour] += h['load_kwh']
    for (day,hour),energy in local_hours.items(): shape[hour].append(energy/daily_totals[day])
    profile = [median(shape[h]) if shape[h] else 1/24 for h in range(24)]
    profile = [v/sum(profile) for v in profile]
    hours_by_day = defaultdict(list)
    for h in feed['weather'].get('hours',[]):
        day = datetime.fromtimestamp(h['time']/1000,tz).date().isoformat()
        hours_by_day[day].append(h)
    battery = feed['battery']
    capacity = battery['capacity_kwh']
    soc = battery['soc']
    stored = capacity*soc/100 if soc is not None else None
    reserve = capacity*battery['reserve_soc']/100
    efficiency = math.sqrt(config['planning_battery_efficiency']/100)
    result = []
    for solar in feed['solar']:
        day = solar['date']
        weather = sorted(hours_by_day.get(day,[]),key=lambda h:h['time'])
        temps = [h['temperature'] for h in weather]
        temp = sum(temps)/len(temps) if temps else None
        load = reference
        if temp is not None:
            if ref_temp is not None:
                load += heat*(max(0,config['planning_heat_base_c']-temp)-max(0,config['planning_heat_base_c']-ref_temp))
                load += cool*(max(0,temp-config['planning_cool_base_c'])-max(0,ref_temp-config['planning_cool_base_c']))
            elif not complete:
                load += heat*max(0,config['planning_heat_base_c']-temp)+cool*max(0,temp-config['planning_cool_base_c'])
        load = max(reference*.3,load)
        uncertainty = .2 if learned else .35
        row = {'date':day,'temperature_min':min(temps) if temps else None,'temperature_max':max(temps) if temps else None,
               'temperature':temp,'clouds':sum(h['clouds'] for h in weather)/len(weather) if weather else None,
               'solar_kwh':solar['energy_kwh'],'load_kwh':load,'load_low_kwh':load*(1-uncertainty),'load_high_kwh':load*(1+uncertainty),
               'import_kwh':None,'export_kwh':None,'balance_ron':None,'battery_end_soc':None,'best_window':None,
               'confidence':'medie' if learned else 'redusa','partial_today':day==now.date().isoformat()}
        solar_map = {h['time']:h['energy_kwh'] for h in solar['hours']}
        solar_complete = all(h['time'] in solar_map for h in weather if h['time']/1000+3600 > now.timestamp())
        if len(weather) >= 20 and solar_complete and solar['energy_kwh'] is not None and stored is not None and battery['charge_kw'] is not None:
            sim_import, sim_export, future_load, future_solar, best = 0.,0.,0.,0.,None
            weights = [profile[datetime.fromtimestamp(h['time']/1000,tz).hour] for h in weather]
            for h,weight in zip(weather,weights):
                stamp = h['time']/1000
                if stamp+3600 <= now.timestamp(): continue
                fraction = max(0,min(1,(stamp+3600-now.timestamp())/3600))
                pv = solar_map.get(h['time'])
                if pv is None: continue
                demand = load*weight/sum(weights)*fraction
                future_load += demand
                future_solar += pv*fraction
                available = pv*fraction-demand
                if available >= 0:
                    charge = min(available, battery['charge_kw']*fraction, max(0,capacity-stored)/efficiency)
                    stored += charge*efficiency
                    export = max(0,available-charge)
                    sim_export += export
                    if best is None or export > best['surplus_kwh']:
                        best = {'time':h['time'],'surplus_kwh':export}
                else:
                    discharge = min(-available, battery['discharge_kw']*fraction, max(0,stored-reserve)*efficiency)
                    stored -= discharge/efficiency
                    sim_import += max(0,-available-discharge)
            actual_import, actual_export = 0.,0.
            if day == now.date().isoformat():
                actual_import,actual_export = feed['today'].get('import_kwh'),feed['today'].get('export_kwh')
                if feed['today'].get('load_kwh') is not None:
                    row['load_kwh'] = feed['today']['load_kwh']+future_load
                    row['load_low_kwh'] = feed['today']['load_kwh']+future_load*(1-uncertainty)
                    row['load_high_kwh'] = feed['today']['load_kwh']+future_load*(1+uncertainty)
                if feed['today'].get('solar_kwh') is not None: row['solar_kwh'] = feed['today']['solar_kwh']+future_solar
                row['solar_actual_kwh'] = feed['today'].get('solar_kwh')
            if actual_import is not None and actual_export is not None:
                row.update(import_kwh=sim_import+actual_import, export_kwh=sim_export+actual_export,
                           battery_end_soc=max(0,min(100,stored/capacity*100)),best_window=best)
                price = tariff(tariffs,day)
                row['balance_ron'] = row['export_kwh']*price['export_price']-row['import_kwh']*price['import_price']
        else:
            stored = None
        result.append(row)
    recommendations = []
    usable = [r for r in result if r['solar_kwh'] is not None]
    if usable:
        best = max(usable,key=lambda r:r['solar_kwh'])
        first = usable[0]
        if first['solar_kwh'] < first['load_kwh']*.5:
            recommendations.append({'title':'Pastreaza energia pentru casa', 'text':f"Pentru {first['date']}, solarul estimat este {first['solar_kwh']:.1f} kWh, fata de {first['load_kwh']:.1f} kWh consum. Amana incarcarea solara Tesla si boosturile optionale.", 'level':'warning'})
        if best['date'] != first['date'] and best['solar_kwh'] > first['solar_kwh']*1.4:
            recommendations.append({'title':'Muta sarcinile flexibile', 'text':f"Ziua {best['date']} are cea mai buna productie estimata: {best['solar_kwh']:.1f} kWh. Programeaza atunci uscatorul sau incarcarea masinii, dupa incarcarea bateriei casei.", 'level':'good'})
        window = max((r for r in usable if r.get('best_window')),key=lambda r:r['best_window']['surplus_kwh'],default=None)
        if window and window['best_window']['surplus_kwh'] >= 1.8:
            hour = datetime.fromtimestamp(window['best_window']['time']/1000,tz).strftime('%H:%M')
            recommendations.append({'title':'Fereastra pentru apa calda', 'text':f"Pe {window['date']}, in jur de {hour}, ramane surplus estimat dupa casa si baterie. Boilerul de 1.8 kW poate stoca energie termica, dupa prioritatea Tesla.", 'level':'good'})
    if any(r['temperature_min'] is not None and r['temperature_min'] <= -5 for r in result):
        recommendations.append({'title':'Pregateste rezerva pentru frig', 'text':'Sunt prognozate temperaturi sub -5 C. Evita sprijinul bateriei pentru sarcini optionale daca prognoza nu permite reincarcarea; profilul Low poate reduce necesarul termic.', 'level':'warning'})
    if not learned:
        recommendations.append({'title':'Estimare orientativa', 'text':f"Sunt {len(complete)} zile complete de consum si {len(paired)} zile cu meteo asociata. Modelul termic ramane conservator pana la minimum 14 zile cu temperaturi masurate.", 'level':'info'})
    if assumed_temperature:
        recommendations.append({'title':'Referinta termica provizorie', 'text':f"In lipsa istoricului meteo asociat, consumul median este raportat provizoriu la {ref_temp:.1f} C, media prognozata azi. Sensibilitatea la frig si caldura este cea reglata de tine, nu una invatata din masuratori.", 'level':'info'})
    return {'days':result,'recommendations':recommendations,'sample_days':len(complete),'weather_sample_days':len(paired),
            'model':'Regresie pe grade-zile' if learned else 'Mediana istorica si sensibilitate termica reglabila',
            'assumptions':{'battery_reserve_soc':battery['reserve_soc'],'battery_capacity_kwh':capacity,
                           'reference_temperature_c':ref_temp,'temperature_reference_assumed':assumed_temperature,
                           'ev_future_energy_kwh':0,'grid_battery_charging':False,'thermal_boosts':False},
            'weather_fetched_at':feed['weather'].get('fetched_at'),'weather_error':feed['weather'].get('error',''),
            'generated_at':feed['now']}
