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

# these imports are outside of the "try" block because it defines
# the function fatal_error(), which is used in the "except"
from misc import *
import sys

try:
	from icons import *
	import os
	import gtk


except Exception, exception:
	fatal_error("Fatal error loading Cardapio's GTK interface", exception)
	sys.exit(1)

if gtk.ver < (2, 14, 0):
	fatal_error("Fatal error loading Cardapio's GTK interface", 'Error! Gtk version must be at least 2.14. You have version %s' % gtk.ver)
	sys.exit(1)


class OptionsWindow:

	def __init__(self, cardapio):

		self.cardapio = cardapio


	def setup_ui(self):

		options_ui_filepath = os.path.join(self.cardapio.cardapio_path, 'ui', 'options.ui')

		builder = gtk.Builder()
		builder.set_translation_domain(self.cardapio.APP)
		builder.add_from_file(options_ui_filepath)
		builder.connect_signals(self.cardapio)

		self.get_widget = builder.get_object
		self.plugin_tree_model      = self.get_widget('PluginListstore')
		self.plugin_checkbox_column = self.get_widget('PluginCheckboxColumn')
		self.dialog                 = self.get_widget('OptionsDialog')

		self.drag_allowed_cursor = gtk.gdk.Cursor(gtk.gdk.FLEUR)


	# This method is required by the View API
	def show(self, state):
		"""
		Shows the "Options" dialog
		"""

		if state : self.dialog.show()
		else     : self.dialog.hide()


	def on_plugintreeview_hover(self, treeview, event):
		"""
		Change the cursor to show that plugins are draggable.
		"""

		pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))

		if pthinfo is None:
			treeview.window.set_cursor(None)
			return

		path, col, cellx, celly = pthinfo

		if col == self.plugin_checkbox_column:
			treeview.window.set_cursor(None)
		else:
			treeview.window.set_cursor(self.drag_allowed_cursor)


