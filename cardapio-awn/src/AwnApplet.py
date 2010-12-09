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

from misc import *
try:
	import gtk
	from CardapioAppletInterface import *

except Exception, exception:
	fatal_error("Fatal error loading Cardapio's applet for Avant Window Navigator", exception)
	sys.exit(1)

from awn.extras import awnlib, __version__

from Cardapio import Cardapio


class AwnApplet(CardapioAppletInterface):

	cardapio_bus_name = 'org.varal.Cardapio'
	cardapio_object_path = '/org/varal/Cardapio'
	cardapio_iface_name = 'org.varal.Cardapio'

	panel_type = PANEL_TYPE_AWN

	def __init__(self, applet):

		self.applet = applet

		self.applet.tooltip.set('Cardapio')

		self.cardapio = Cardapio(show = Cardapio.DONT_SHOW, panel_applet = self)

		self.preferences = gtk.ImageMenuItem(gtk.STOCK_PREFERENCES)
		self.edit = gtk.ImageMenuItem(gtk.STOCK_EDIT)
		self.about = gtk.ImageMenuItem(gtk.STOCK_ABOUT)

		self.preferences.connect('activate', self.cardapio.open_options_dialog)
		self.edit.connect('activate', self.cardapio.launch_edit_app)
		self.about.connect('activate', self.cardapio.open_about_dialog)

		self.menu = self.applet.dialog.menu
		self.menu.insert(self.preferences, 0)
		self.menu.insert(self.edit, 1)
		self.menu.insert(self.about, 2)
		self.menu.insert(gtk.SeparatorMenuItem(), 3)
		self.menu.show_all()

		self.applet.connect('clicked', self._on_applet_clicked)


	def setup(self, cardapio):
		pass


	def update_from_user_settings(self, settings):

		if settings['open on hover']:
			self.applet.connect('enter-notify-event', self._on_applet_cursor_enter)
		# TODO: else?


	def get_size(self):
		# TODO: check that this does indeed give us what we expect it does
		return self.applet.get_window().get_size()


	def get_position(self):
		# TODO: check that this does indeed give us what we expect it does
		return self.applet.get_window().get_origin()


	def get_orientation(self):

		pos_type = self.applet.get_pos_type()
		if pos_type == gtk.POS_TOP    : return POS_TOP
		if pos_type == gtk.POS_BOTTOM : return POS_BOTTOM
		if pos_type == gtk.POS_LEFT   : return POS_LEFT
		else: return POS_RIGHT


	def has_mouse_cursor(self, mouse_x, mouse_y):
		return False


	def draw_toggled_state(self, state):
		pass

	def _on_applet_clicked(self, widget):
		self.cardapio.show_hide()

	def _on_applet_cursor_enter(self, widget, event):
		self.cardapio.show_hide()
		return True


