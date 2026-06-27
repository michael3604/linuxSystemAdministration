#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys
from pathlib import Path

from atomic import atomic_write_text
from config import load_config
from timeutil import now_text

NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*$')


def usage() -> int:
    print('usage: createDataPoint <serviceName> <status> <text>')
    print('   or: createDataPoint <serviceName> <status> <value> <unit> <text>')
    return 2


def main(argv: list[str]) -> int:
    if len(argv) not in (4, 6):
        return usage()
    _, service, status, *rest = argv
    if not NAME_RE.match(service):
        print(f'invalid service name: {service}', file=sys.stderr)
        return 2
    data = {'timestamp': now_text(), 'status': status}
    if len(rest) == 1:
        data['text'] = rest[0]
    else:
        value, unit, text = rest
        try:
            data['value'] = float(value)
        except ValueError:
            print(f'invalid numeric value: {value}', file=sys.stderr)
            return 2
        data['unit'] = unit
        data['text'] = text
    cfg = load_config()
    local = Path(cfg['paths']['localDataFolder'])
    atomic_write_text(local / f'{service}.json', json.dumps(data, indent=2, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
