# Copyright (C) 2010 Pawel Bara (keirangtp at gmail com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import pygtk
pygtk.require('2.0')
import gtk

from awn.extras import awnlib, __version__

from Cardapio import *


class CardapioApplet:

	cardapio_bus_name = 'org.varal.Cardapio'
	cardapio_object_path = '/org/varal/Cardapio'
	cardapio_iface_name = 'org.varal.Cardapio'

	def __init__(self, applet):
		self.applet = applet

		self.applet.tooltip.set("Cardapio")

		self.cardapio_app = Cardapio(applet_type = Cardapio.APPLET_TYPE_AWN, panel_applet = applet)

		self.preferences = gtk.ImageMenuItem(gtk.STOCK_PREFERENCES)
		self.edit = gtk.ImageMenuItem(gtk.STOCK_EDIT)
		self.about = gtk.ImageMenuItem(gtk.STOCK_ABOUT)

		self.preferences.connect("activate", self.cardapio_app.open_options_dialog)
		self.edit.connect("activate", self.cardapio_app.launch_edit_app)
		self.about.connect("activate", self.cardapio_app.open_about_dialog)

		self.menu = self.applet.dialog.menu
		self.menu.insert(self.preferences, 0)
		self.menu.insert(self.edit, 1)
		self.menu.insert(self.about, 2)
		self.menu.insert(gtk.SeparatorMenuItem(), 3)
		self.menu.show_all()

		self.applet.connect("clicked", self.applet_clicked)

		# making 'open on hover' sort-of work (hovering works like a click)
		if self.cardapio_app.settings['open on hover']:
			self.applet.connect('enter-notify-event', self.cardapio_app.on_applet_cursor_enter)


	def applet_clicked(self, widget):
		self.cardapio_app.show_hide()



if __name__ == "__main__":
	awnlib.init_start(CardapioApplet, {
		"name"           : "Cardapio's applet",
		"short"          : "cardapio",
		"version"        : __version__,
		"description"    : "Replace your menu with Cardapio",
		"theme"          : "cardapio-256",
		"author"         : "Keiran",
		"copyright-year" : "2010",
		"authors"        : [ "Pawel Bara" ]
	})
