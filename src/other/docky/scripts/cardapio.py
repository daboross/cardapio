#!/usr/bin/env python

import atexit
import gobject

try:
	from dockmanager.dockmanager import DockManagerItem, DockManagerSink, DOCKITEM_IFACE
	from signal import signal, SIGTERM
	from sys import exit
except ImportError, e:
	exit()

class CardapioItem(DockManagerItem):

	def __init__(self, sink, path):
		DockManagerItem.__init__(self, sink, path)

		# TODO: this stuff duplicates on reinstall
		self.add_menu_item("Properties", "gtk-properties", "")
		self.add_menu_item("Edit menus", "gtk-edit", "")

		self.add_menu_item("About Cardapio", "gtk-about", "Informations")
		self.add_menu_item("About Gnome", "", "Informations")
		self.add_menu_item("About Ubuntu", "", "Informations")

class CardapioSink(DockManagerSink):

	iface_name = "org.freedesktop.DBus.Properties"
	desktop_name = "cardapio.desktop"

	def item_path_found(self, pathtoitem, item):
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