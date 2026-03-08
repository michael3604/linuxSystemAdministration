# SPDX-License-Identifier: BSD-2-Clause

import datetime
import subprocess
import operator
import time
import syslog
from configparser import ConfigParser

class ZfsSnapshot:
	'''Represents a single ZFS snapshot.'''
	def __init__ (self, path, name, date):
		self._path = path
		self._name = name
		self._date = date

	@property
	def Timestamp (self):
		return self._date

	@property
	def Name (self):
		return self._name

	@property
	def Path (self):
		return self._path

	def __str__ (self):
		return 'Snapshot: {}@{} : {}'.format (self._path, self._name, self._date)

	def __repr__ (self):
		return 'ZfsSnapshot ({}, {}, {})'.format (repr (self._path),
			repr (self._name),
			repr (self._date))

	def __hash__ (self):
		return hash(self.__key ())

	def __eq__ (self, other):
		return self.__key () == other.__key ()

	def __key (self):
		return (self._path, self._name, self._date)

def GetSnapshots (pool):
	'''Get all snapshots for a pool as a list of ZfsSnapshot.

	All means all snapshots created using this tool, that is, snapshots starting
	with shadow_copy -- for those, we know the time zone.'''
	s = subprocess.check_output (['zfs', 'list', '-Ht', 'snapshot', '-o', 'name']).decode ('utf-8').split ('\n')
	snapshotNames = [l.strip () for l in s if l]
	snapshots = []

	for n in snapshotNames:
		path = n [:n.find ('@')]

		if path != pool:
			continue

		nameDate = n [n.find ('@')+1:]
		name = None
		timestamp = None
		if nameDate.startswith ('shadow_copy'):
			name = 'shadow_copy'
			# Our snapshots are in UTC time
			timestampUtcTime = time.strptime (nameDate [nameDate.find ('-')+1:],
				'%Y.%m.%d-%H.%M.%S')
			timestamp = datetime.datetime (*(timestampUtcTime [0:6]),
				tzinfo=datetime.timezone.utc)
		else:
			# unknown format, can't parse date, so ignore and continue
			continue

		snapshots.append (ZfsSnapshot (path, name, timestamp))

	return snapshots

def CreateSnapshot (path, recursive=True, dryRun = False):
	'''Create a shadow copy snapshot for the pool or filesystem.'''
	dt = datetime.datetime.utcnow ()
	snapshotName = dt.strftime ('shadow_copy-%Y.%m.%d-%H.%M.%S')

	args = ['zfs', 'snapshot']
	if recursive:
		args.append ('-r')
	args.append ('{}@{}'.format (path, snapshotName))

	if dryRun:
		print (' '.join (args))
	else:
		subprocess.check_call (args)
		syslog.syslog (syslog.LOG_INFO,
			'Created snapshot: {}@{}'.format (path, snapshotName))

	return ZfsSnapshot (path, 'shadow_copy', dt)

def DestroySnapshot (path, snapshot, recursive=True, dryRun = False):
	'''Destroy a shadow copy snapshot in the provided pool.'''
	# Safety checks
	if snapshot.Name != 'shadow_copy':
		return

	if snapshot.Path != path:
		return

	snapshotName = snapshot.Timestamp.strftime ('shadow_copy-%Y.%m.%d-%H.%M.%S')

	args = ['zfs', 'destroy']
	if recursive:
		args.append ('-r')
	args.append ('{}@{}'.format (path, snapshotName))

	if dryRun:
		print (' '.join (args))
	else:
		subprocess.check_call (args)
		syslog.syslog (syslog.LOG_INFO,
			'Destroyed snapshot: {}@{}'.format (path, snapshotName))

def GetPools ():
	'''Find all ZFS pools.'''
	zp = subprocess.check_output (['zpool', 'list', '-H', '-o', 'name']).decode ('utf-8').split ('\n')
	return [l.strip () for l in zp if l]

def GetFilesystems ():
	zp = subprocess.check_output (['zfs', 'list', '-H', '-t', 'filesystem', '-o', 'name']).decode ('utf-8').split ('\n')
	return [l.strip () for l in zp if l]

class Filter:
	'''Filters a list of snapshots.'''
	def Apply (self, snapshots):
		return snapshots

class PassthroughFilter(Filter):
	pass

class BucketFilter (Filter):
	'''Filter snapshots into a bucket. The bucket groups snapshots together,
	and the filter returns the newest item in each bucket.

	The ``GetBucket`` function determines which bucket a snapshot belongs to.'''
	def GetBucket (self, timestamp):
		return timestamp

	def Apply (self, snapshots):
		buckets = {}

		for snapshot in snapshots:
			bucket = self.GetBucket (snapshot.Timestamp)
			if bucket not in buckets:
				buckets [bucket] = []
			buckets [bucket].append (snapshot)
		return self.GetNewestPerBucket (buckets)

	def GetNewestPerBucket (self, buckets):
		'''Buckets must be a dictionary [bucket] -> list of snapshots.

		This will return the newest snapshot in each bucket.'''
		result = []

		for bucket in buckets.values ():
			result.append (sorted (bucket, key=operator.attrgetter ('Timestamp')) [-1])

		return result

class HourlyFilter (BucketFilter):
	def GetBucket (self, timestamp):
		return datetime.datetime (year=timestamp.year,
			month=timestamp.month, day=timestamp.day, hour=timestamp.hour,
			tzinfo=timestamp.tzinfo)

class DailyFilter (BucketFilter):
	def GetBucket (self, timestamp):
		return datetime.datetime (year=timestamp.year,
			month=timestamp.month, day=timestamp.day,
			tzinfo=timestamp.tzinfo)

class WeeklyFilter (BucketFilter):
	def GetBucket (self, timestamp):
		iso = timestamp.isocalendar ()
		return (iso [0], iso [1],)

class MonthlyFilter (BucketFilter):
	def GetBucket (self, timestamp):
		return datetime.datetime (year=timestamp.year,
			month=timestamp.month, day=1, tzinfo=timestamp.tzinfo)

class YearlyFilter (BucketFilter):
	def GetBucket (self, timestamp):
		return datetime.datetime (year=timestamp.year,
			month=1, day=1, tzinfo=timestamp.tzinfo)

__DEFAULT_FILTERS = [
	# Filter name; maximum age until this filter should get applied
	(PassthroughFilter (), datetime.timedelta (days=2)),
	(HourlyFilter (), datetime.timedelta (days=7)),
	(DailyFilter (), datetime.timedelta (days=30)),
	(WeeklyFilter (), datetime.timedelta (days=90)),
	(MonthlyFilter (), datetime.timedelta (days=365)),
	(YearlyFilter, datetime.timedelta.max),
]

def __BuildFilters (s):
	filters = [
		('all', PassthroughFilter,),
		('hourly', HourlyFilter,),
		('daily', DailyFilter,),
		('weekly', WeeklyFilter,),
		('monthly', MonthlyFilter,),
		('yearly', YearlyFilter,),
	]

	result = []
	for filterName, filterClass in filters:
		if filterName in s:
			cutoff = s [filterName]

			if cutoff == '0' or cutoff == 'disabled':
				continue

			if cutoff == 'unlimited':
				cutoff = datetime.timedelta.max
			else:
				cutoff = datetime.timedelta (int(cutoff))
			result.append ((filterClass (), cutoff,))

	return result

def ParseConfiguration (configFile):
	config = ConfigParser ()
	config.read_file (configFile)

	result = {}
	for section in config.sections ():
		result [section] = {'filters' : __BuildFilters (config [section])}

		# Must match the default config below
		result [section]['recursive'] = config.getboolean (section, 'recursive', fallback=True)
		result [section]['ignore'] = config.getboolean (section, 'ignore', fallback=False)

	if '_default' not in config:
		result.update (GetDefaultConfiguration ())

	return result

def GetDefaultConfiguration ():
	return {'_default' : {
		'filters' : __DEFAULT_FILTERS,
		'recursive' : True,
		'ignore' : False}
	}

def FilterSnapshots (snapshots,
	currentTime = datetime.datetime.now (datetime.timezone.utc),
	filters = __DEFAULT_FILTERS):
	'''Filter snapshots and return a tuple of snapshots to keep and to delete.'''
	def Partition (l, condition):
		'''Partition a list into a two lists based on a condition.

		Returns a tuple, the first items contains a list of all elements for
		which the condition was true, the second all for which it was false.'''
		trueList = []
		falseList = []
		for element in l:
			if condition (element):
				trueList.append (element)
			else:
				falseList.append (element)
		return (trueList, falseList)

	toKeep = set ()
	remainingSnapshots = snapshots

	for currentFilter, cutoff in filters:
		if not remainingSnapshots:
			break
		# Partition such that currentSnapshots are all < cutoff
		currentSnapshots, remainingSnapshots = Partition (remainingSnapshots,
			# The assumption is that currentTime is always >= snapshot.Timestamp
			lambda snapshot: (currentTime - snapshot.Timestamp) <= cutoff)
		toKeep.update (currentFilter.Apply (currentSnapshots))

	# If some entries remain, we want to keep them, as they're even older
	# and there was no policy set for very old snapshots
	toKeep.update (remainingSnapshots)

	toDelete = set (snapshots)
	toDelete.difference_update (toKeep)

	# Deleting in reversed order is supposed to be better
	# http://serverfault.com/questions/340837/how-to-delete-all-but-last-n-zfs-snapshots
	# Doesn't cost us much to do it here, so why not
	return (toKeep,
		sorted (toDelete, key=operator.attrgetter ('Timestamp'), reverse=True))

