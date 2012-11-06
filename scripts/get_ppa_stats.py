#!/usr/bin/python

from launchpadlib.launchpad import Launchpad
PPAOWNER = "cardapio-team" # the launchpad PPA owener. It's usually the first part of a PPA. Example: in "webupd8team/vlmc", the owner is "webupd8team".
PPA = "unstable"           # the PPA to get stats for. It's the second part of a PPA. Example: in "webupd8team/vlmc", the PPA is "vlmc"

dists = ['quantal', 'precise', 'oneiric', 'natty', 'maverick', 'lucid']
archs = ['i386', 'amd64']

url = r'https://api.launchpad.net/devel/ubuntu/%s/%s'


cachedir = "~/.launchpadlib/cache/"

lp_ = Launchpad.login_anonymously('ppastats', 'edge', cachedir, version='devel')
owner = lp_.people[PPAOWNER]
archive = owner.getPPAByName(name=PPA)


print '\n+=============================================================+'
print   '| Note: These counts get reset every time you update the PPA! |'
print   '+=============================================================+'

for dist in dists:
	for arch in archs:
		desired_dist_and_arch = url % (dist, arch)
		print '\nDist: %s, Arch: %s' % (dist, arch)

		for individualarchive in archive.getPublishedBinaries(status='Published', distro_arch_series=desired_dist_and_arch):
			print ' * % -20s % -30s % 6s' % (individualarchive.binary_package_name, individualarchive.binary_package_version, str(individualarchive.getDownloadCount()))
