#!/usr/bin/env python

import atexit
import gobject

import dbus

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
