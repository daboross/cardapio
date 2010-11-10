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


class DockySettingsHelper:
	"""
	Parser of Docky's GConf settings.
	"""

	# GConf root of Docky's settings
	docky_gconf_root = '/apps/docky-2/Docky'
	docky_dcontroller_gconf_root = docky_gconf_root + '/DockController/'
	docky_iface_gconf_root = docky_gconf_root + '/Interface/DockPreferences/'

	# name of Cardapio's launcher
	cardapio_desktop = 'cardapio.desktop'

	gconf_client = gconf.client_get_default()


	def __init__(self):
		self.active_docks = self.gconf_client.get_list(self.docky_dcontroller_gconf_root + 'ActiveDocks', gconf.VALUE_STRING)


	# NOTE: This method is cloned in DockySettingsHelper.py	
	def get_dock_for_this_helper(self):
		"""
		Returns the name of the dock in which it finds the launcher for
		Cardapio. If there's none or there is more than one dock,
		LauncherError is raised.
		"""

		docks = filter(lambda dock:

			filter(lambda launcher:
				launcher.endswith(self.cardapio_desktop),
			self.gconf_client.get_list(self.docky_iface_gconf_root + dock + '/Launchers', gconf.VALUE_STRING)),

		self.active_docks)

		if len(docks) != 1:
			raise LauncherError(len(docks))

		return docks[0]


	def get_main_dock(self):
		"""
		Returns the name of the main Docky's dock (the one that keeps the
		unknown launchers). If there's none, raises MainDockError and if
		there are more, returns the first one's name.
		"""

		main_docks = filter(lambda dock:
			self.gconf_client.get_bool(self.docky_iface_gconf_root + dock + '/WindowManager'),
		self.active_docks)

		if len(main_docks) == 0:
			raise MainDockError

		return main_docks[0]


	def add_launcher(self, dock, launcher):
		launchers = settings_helper.gconf_client.get_list(self.docky_iface_gconf_root + dock + '/Launchers', gconf.VALUE_STRING)
		launchers.insert(0, launcher)

		settings_helper.gconf_client.set_list(self.docky_iface_gconf_root + dock + '/Launchers', gconf.VALUE_STRING, launchers)



# NOTE: This class is cloned in DockySettingsHelper.py
class LauncherError(Exception):

	def __init__(self, launcher_count):
		self.launcher_count = launcher_count



class MainDockError(Exception):
	pass


# initialization phase that happens when Docky loads our helper;
# if there's no launcher for Cardapio on docks, this tries to
# add it programatically (will require Docky's restart though)

settings_helper = DockySettingsHelper()

try:

	dock_num = settings_helper.get_dock_for_this_helper()
	
# user has none or more than one launcher?
except LauncherError, e:
	# if he has more - it's his problem; if he has none on the
	# other hand...
	if e.launcher_count == 0:

		try:

			# let's add the launcher to the main dock (visible
			# after restart)
			main_dock = settings_helper.get_main_dock()
			settings_helper.add_launcher(main_dock, 'file:///usr/lib/cardapio/cardapio.desktop')

		except MainDockError:
			# no main dock? we can't do anything here
			pass



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
