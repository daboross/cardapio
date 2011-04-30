#!/usr/bin/env python

#  
#  Copyright (C) 2010 Cardapio Team (tvst@hotmail.com)
# 
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
# 
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

try:
 	from dockmanager.dockmanager import DockManagerSink

	from sys import exit
	from signal import signal, SIGTERM

	import os
	import gconf
	import atexit
	import gobject
	import subprocess

except ImportError, e:
	print(e)
	exit(255)


# note - this is duplicated in misc.py
def which(filename):
	"""
	Searches the folders in the OS's PATH variable, looking for a file called
	"filename". If found, returns the full path. Otherwise, returns None.
	"""

	for path in os.environ["PATH"].split(os.pathsep):
		if os.access(os.path.join(path, filename), os.X_OK):
			return "%s/%s" % (path, filename)
	return None


docky_item_gconf_root = '/apps/docky-2/Docky/Items/DockyItem'


def install_cardapio_launcher():
	"""
	Sets Docky up so that Cardapio is launched whenever the dock icon is clicked.
	"""

	gconf_client = gconf.client_get_default()

	cardapio_cmd = which('cardapio')

	if cardapio_cmd == None: 
		print "Error! Cardapio not found!"
		exit(254)

	new_command = cardapio_cmd + ' docky-open'
	new_label   = ''

	current_command = gconf_client.get_string(docky_item_gconf_root + '/DockyItemCommand')
	#current_label   = gconf_client.get_string(docky_item_gconf_root + '/HoverText')

	if current_command != new_command:
		if current_command is not None and current_command != '':
			if 'cardapio' not in current_command:
				gconf_client.set_string(docky_item_gconf_root + '/OldDockyItemCommand', current_command)

		try    : gconf_client.set_string(docky_item_gconf_root + '/DockyItemCommand', new_command)
		except : pass

	#if current_label != '':
	#	if current_label is not None:
	#		gconf_client.set_string(docky_item_gconf_root + '/OldHoverText', current_label)

	#	try    : gconf_client.set_string(docky_item_gconf_root + '/HoverText', '')
	#	except : pass


def remove_cardapio_launcher():
	"""
	Resets Docky to its initial state, before Cardapio ever loaded.
	"""

	gconf_client = gconf.client_get_default()

	current_command = gconf_client.get_string(docky_item_gconf_root + '/DockyItemCommand')
	#current_label   = gconf_client.get_string(docky_item_gconf_root + '/HoverText')

	if current_command == which('cardapio') + ' docky-open':

		old_command = gconf_client.get_string(docky_item_gconf_root + '/OldDockyItemCommand')

		if old_command is not None and old_command != '':
			gconf_client.set_string(docky_item_gconf_root + '/DockyItemCommand', old_command)
		else:
			gconf_client.set_string(docky_item_gconf_root + '/DockyItemCommand', '')

		try    : gconf_client.unset(docky_item_gconf_root + '/OldDockyItemCommand')
		except : pass

	#if current_label == '':

	#	old_label = gconf_client.get_string(docky_item_gconf_root + '/OldHoverText')

	#	if old_label is not None and old_label != '':
	#		gconf_client.set_string(docky_item_gconf_root + '/HoverText', old_label)
	#	else:
	#		gconf_client.set_string(docky_item_gconf_root + '/HoverText', '')

	#	try    : gconf_client.unset(docky_item_gconf_root + '/OldHoverText')
	#	except : pass



class CardapioSink(DockManagerSink):
	"""
	This is not attaching any helpers - just waiting for the signal
	to close.
	"""

	def item_path_found(self, pathtoitem, item): pass


cardapio_sink = CardapioSink()


def cleanup():
	remove_cardapio_launcher()
	cardapio_sink.dispose()


if __name__ == "__main__":
	install_cardapio_launcher()
	subprocess.Popen('cardapio hidden', shell = True)

	mainloop = gobject.MainLoop(is_running = True)

	atexit.register (cleanup)
	signal(SIGTERM, lambda signum, stack_frame: exit(253))

	mainloop.run()

