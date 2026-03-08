#!/usr/bin/env python3

# SPDX-License-Identifier: BSD-2-Clause

from zfs import (
	CreateSnapshot,
	DestroySnapshot,
	FilterSnapshots,
	GetFilesystems,
	GetPools,
	GetSnapshots,
	ParseConfiguration,
	GetDefaultConfiguration,
)

import syslog
import argparse

if __name__=='__main__':
	parser = argparse.ArgumentParser ()
	parser.add_argument ('-c', '--config', type=argparse.FileType ('r'))
	parser.add_argument ('--dry-run', action='store_true')

	args = parser.parse_args ()

	if args.config is not None:
		config = ParseConfiguration (args.config)
	else:
		config = GetDefaultConfiguration ()

	syslog.openlog('zfs-snapshot')

	for pool in GetPools ():
		syslog.syslog (syslog.LOG_INFO,
			'Processing pool "{0}"'.format (pool))

		if pool in config:
			recursive = config [pool]['recursive']
			ignore = config [pool]['ignore']
		else:
			recursive = config ['_default']['recursive']
			ignore = config ['_default']['ignore']

		if ignore:
			syslog.syslog (syslog.LOG_INFO,
				f'Skipping pool "{pool}"')
			continue

		CreateSnapshot (pool, dryRun = args.dry_run, recursive = recursive)

	for filesystem in GetFilesystems ():
		snapshots = GetSnapshots (filesystem)

		if filesystem in config:
			if config [filesystem]['ignore']:
				syslog.syslog (syslog.LOG_INFO,
					f'Skipping filesystem "{filesystem}"')
				continue
			activeSnapshots, obsoleteSnapshots = FilterSnapshots (snapshots,
				filters=config [filesystem]['filters'])
		else:
			activeSnapshots, obsoleteSnapshots = FilterSnapshots (snapshots,
				filters=config ['_default']['filters'])

		for snapshot in obsoleteSnapshots:
			DestroySnapshot (filesystem, snapshot, recursive = False, dryRun = args.dry_run)

