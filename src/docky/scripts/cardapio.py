#!/usr/bin/env python

#
#    Cardapio is an alternative Gnome menu applet, launcher, and much more!
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


import atexit
import gobject

import dbus
import gconf

try:
	from dockmanager.dockmanager import DockManagerItem, DockManagerSink, DOCKITEM_IFACE
	from signal import signal, SIGTERM
	from sys import exit

except ImportError, e:
	exit()

class CardapioItem(DockManagerItem):

	def __init__(self, sink, path):
		DockManagerItem.__init__(self, sink, path)

		self.add_menu_item("Properties", "gtk-properties", "")
		self.add_menu_item("Edit menus", "gtk-edit", "")

		self.add_menu_item("About Cardapio", "gtk-about", "Informations")

		# prepare D-Bus connection with Cardapio
		self.cardapio = None

		self.cardapio_bus_name = 'org.varal.Cardapio'
		self.cardapio_object_path = '/org/varal/Cardapio'
		self.cardapio_iface_name = 'org.varal.Cardapio'

		self.bus = dbus.SessionBus()
		# we track Cardapio's on / off status
		self.bus.watch_name_owner(self.cardapio_bus_name, self.on_dbus_name_change)

#		# find out Cardapio's path in this system
#		import os, commands, sys
#		cardapio_bin = commands.getoutput('which cardapio')
#		cardapio_real_bin = os.path.realpath(cardapio_bin)
#		cardapio_path, dummy = os.path.split(cardapio_real_bin)
#		os.chdir(os.path.join(cardapio_path, 'docky'))
#
#		# see if Cardapio is already on Docky
#		DockySettingsHelper = __import__(DockySettingsHelper)
#		settings_helper = DockySettingsHelper.DockySettingsHelper()
#
#		try: res = settings_helper.get_dock_for_this_helper() # (can return None)
#		except: res = None
#
#		# if Cardapio is not on Docky, add it
#		if res is None:
#			launchers = settings_helper.gconf_client.get_list('/apps/docky-2/Docky/Interface/DockPreferences/Dock1/Launchers', gconf.VALUE_STRING)
#			launchers.insert(0, 'file://' + cardapio_path + '/Cardapio.desktop')
#			settings_helper.gconf_client.set_list('/apps/docky-2/Docky/Interface/DockPreferences/Dock1/Launchers', gconf.VALUE_STRING, launchers)


	def on_dbus_name_change(self, connection_name):
		"""
		This method effectively tracks down the events of Cardapio app starting
		and shutting down. When the app shuts down, this callback nullifies our
		Cardapio's proxy and when the app starts, the callback sets the valid
		proxy again.
		"""

		if len(connection_name) == 0:
			self.cardapio = None
		else:
			bus_object = self.bus.get_object(connection_name, self.cardapio_object_path)
			self.cardapio = dbus.Interface(bus_object, self.cardapio_iface_name)

  	def menu_pressed(self, menu_id):

		if self.cardapio is None:
			return
		
 		if self.id_map[menu_id] == "Properties":
			self.cardapio.open_options_dialog()
 		elif self.id_map[menu_id] == "Edit menus":
			self.cardapio.launch_edit_app()
 		elif self.id_map[menu_id] == "About Cardapio":
			self.cardapio.open_about_cardapio_dialog()
			

class CardapioSink(DockManagerSink):

	iface_name = "org.freedesktop.DBus.Properties"
	desktop_name = "cardapio.desktop"

	def item_path_found(self, pathtoitem, item):
		# TODO: this duplicates menu entries on helper's reinstall
		if item.Get(DOCKITEM_IFACE, "DesktopFile", dbus_interface = self.iface_name).endswith(self.desktop_name):
			self.items[pathtoitem] = CardapioItem(self, pathtoitem)

cardapio_sink = CardapioSink()

def cleanup():
	cardapio_sink.dispose()

if __name__ == "__main__":
	mainloop = gobject.MainLoop(is_running = True)

	atexit.register(cleanup)
	signal(SIGTERM, lambda signum, stack_frame: exit(1))

	mainloop.run()

