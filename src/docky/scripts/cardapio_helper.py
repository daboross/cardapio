#!/usr/bin/env python

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

try:

	import atexit
	import gobject

	from dockmanager.dockmanager import DockManagerItem, DockManagerSink, DOCKITEM_IFACE
	from signal import signal, SIGTERM
	from sys import exit

	import gconf
	import dbus

except ImportError, e:
	exit()


class DockySettingsHelper:
	"""
	Helper class for dealing with Docky's GConf settings.
	"""

	# GConf keys of Docky's settings
	docky_gconf_root = '/apps/docky-2/Docky'
	docky_dcontroller_gconf_root = docky_gconf_root + '/DockController/'
	docky_iface_gconf_root = docky_gconf_root + '/Interface/DockPreferences/'

	# name of Cardapio's launcher
	cardapio_desktop = 'cardapio.desktop'

	gconf_client = gconf.client_get_default()


	def __init__(self):
		# sets the names of user's active docks
		self.active_docks = self.gconf_client.get_list(self.docky_dcontroller_gconf_root + 'ActiveDocks', gconf.VALUE_STRING)


	# NOTE: This method is cloned in DockySettingsHelper.py	
	def get_dock_for_this_helper(self):
		"""
		Returns the name of the dock in which it finds the launcher for
		Cardapio. If there's none or there is more than one dock,
		LauncherError is raised.
		"""

		docks_with_cardapio = []

		for dock in self.active_docks:

			dock_launchers = self.gconf_client.get_list(self.docky_iface_gconf_root + dock + '/Launchers', gconf.VALUE_STRING)
			cardapio_launchers = filter(lambda launcher: launcher.endswith(self.cardapio_desktop), dock_launchers)

			# multiple Cardapio launchers on one dock
			if(len(cardapio_launchers) > 1):
				raise LauncherError(True)
			elif len(cardapio_launchers) == 1:
				docks_with_cardapio.append(dock)

		# multiple docks with Cardapio launchers
		if len(docks_with_cardapio) != 1:
			raise LauncherError(len(docks_with_cardapio) > 1)

		return docks_with_cardapio[0]


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
		"""
		Adds a new launcher to one of Docky's docks by pushing it into
		it's GConf settings.
		"""

		launchers = settings_helper.gconf_client.get_list(self.docky_iface_gconf_root + dock + '/Launchers', gconf.VALUE_STRING)
		launchers.insert(0, launcher)

		settings_helper.gconf_client.set_list(self.docky_iface_gconf_root + dock + '/Launchers', gconf.VALUE_STRING, launchers)



# NOTE: This class is cloned in DockySettingsHelper.py
class LauncherError(Exception):
	"""
	Exception raised when there are none or multiple Cardapio launchers on
	Docky's docks. The "multiple" flag says whether there were many or none.
	"""

	def __init__(self, multiple):
		self.multiple = multiple


class MainDockError(Exception):
	"""
	Exception raised when the DockySettingsHelper is unable to find the
	main dock of Docky.
	"""

	pass

# TODO: duplication of DockySettingsHelper code - here (helper) and inside
# main Cardapio
# TODO: is there a better way to put a new launcher on Docky from code?
# TODO: is there a way to restart Docky from code? our launcher appears
# after a restart of Docky because Docky's not watching it's GConf settings

# initialization phase that happens when Docky loads our helper;
# if there's no launcher for Cardapio on docks, this tries to
# add one

settings_helper = DockySettingsHelper()

try:

	dock_num = settings_helper.get_dock_for_this_helper()
	
# user has none or more than one launcher?
except LauncherError, e:
	# if he has more - it's his problem; if he has none on the
	# other hand...
	if not e.multiple:

		try:

			# let's add the launcher to the main dock (visible
			# after restart)
			main_dock = settings_helper.get_main_dock()
			settings_helper.add_launcher(main_dock, 'file:///usr/lib/cardapio/cardapio.desktop')

		except MainDockError:
			# no main dock? we can't do anything here
			pass



class CardapioItem(DockManagerItem):
	"""
	Main Cardapio's helper class.
	"""

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
	"""
	Sink of Cardapio's helper.
	"""

	iface_name = "org.freedesktop.DBus.Properties"
	desktop_name = "cardapio.desktop"

	def item_path_found(self, pathtoitem, item):
		# TODO: this duplicates menu entries on helper's reinstall
		if item.Get(DOCKITEM_IFACE, "DesktopFile", dbus_interface = self.iface_name).endswith(self.desktop_name):
			self.items[pathtoitem] = CardapioItem(self, pathtoitem)



# run the helper
cardapio_sink = CardapioSink()

def cleanup():
	cardapio_sink.dispose()

if __name__ == "__main__":
	mainloop = gobject.MainLoop(is_running = True)

	atexit.register(cleanup)
	signal(SIGTERM, lambda signum, stack_frame: exit(1))

	mainloop.run()
