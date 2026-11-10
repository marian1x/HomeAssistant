"""Calendar-effective tariffs. Before the first known tariff, the baseline is assumed."""
from datetime import date


def initial(c):
    values = {'import_price': c['energy_import_price'], 'export_price': c['energy_export_price']}
    return [{'from': '1970-01-01', **values, 'assumed': True}, {'from': c['energy_tariff_from'], **values, 'assumed': False}]


def update(history, c):
    day = c['energy_tariff_from']
    row = {'from': day, 'import_price': c['energy_import_price'], 'export_price': c['energy_export_price'], 'assumed': False}
    return sorted([r for r in history if r['from'] != day] + [row], key=lambda r:r['from'])


def active(history, day):
    return max((r for r in history if r['from'] <= day), key=lambda r:r['from'])
