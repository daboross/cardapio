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
	import os
	import gtk
	from CardapioAppletInterface import PANEL_TYPE_DOCKY, PANEL_TYPE_AWN 


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
		"""
		Builds the OptionsWindow GUI
		"""

		options_ui_filepath = os.path.join(self.cardapio.cardapio_path, 'ui', 'options.ui')

		builder = gtk.Builder()
		builder.set_translation_domain(self.cardapio.APP)
		builder.add_from_file(options_ui_filepath)
		builder.connect_signals(self)

		self.get_widget = builder.get_object
		self.plugin_tree_model      = self.get_widget('PluginListstore')
		self.plugin_checkbox_column = self.get_widget('PluginCheckboxColumn')
		self.dialog                 = self.get_widget('OptionsDialog')

		self.drag_allowed_cursor = gtk.gdk.Cursor(gtk.gdk.FLEUR)

		self.prepare_panel_related_options()
		self.read_gtk_theme_info()


	def read_gtk_theme_info(self):
		"""
		Reads some info from the GTK theme to better adapt to it 
		"""

		scrollbar = gtk.VScrollbar()
		self.scrollbar_width = scrollbar.style_get_property('slider-width')


	def prepare_panel_related_options(self):
		"""
		Show or hide widgets in the options window depending on whether they
		are supported by the current panel (if any)
		"""

		if self.cardapio.panel_applet is None \
				or self.cardapio.panel_applet.panel_type == PANEL_TYPE_DOCKY:
			self.get_widget('AppletOptionPane').hide()

		elif self.cardapio.panel_applet.panel_type is PANEL_TYPE_AWN:
			self.get_widget('LabelAppletLabel').hide()
			self.get_widget('OptionAppletLabel').hide()


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


	def show(self):
		"""
		Show the Options Dialog and populate its widgets with values from the
		user's settings.
		"""

		self.is_change_handler_blocked = True

		self.set_widget_from_option('OptionKeybinding', 'keybinding')
		self.set_widget_from_option('OptionAppletLabel', 'applet label')
		self.set_widget_from_option('OptionAppletIcon', 'applet icon')
		self.set_widget_from_option('OptionSessionButtons', 'show session buttons')
		self.set_widget_from_option('OptionKeepResults', 'keep search results')
		self.set_widget_from_option('OptionOpenOnHover', 'open on hover')
		self.set_widget_from_option('OptionOpenCategoriesOnHover', 'open categories on hover')
		self.set_widget_from_option('OptionMiniMode', 'mini mode')

		icon_size = gtk.icon_size_lookup(4)[0] # 4 because it's that same as in the UI file

		self.plugin_tree_model.clear()

		for plugin_tuple in self.cardapio.plugin_iterator():

			basename, plugin_info, is_active, is_core, is_required = plugin_tuple

			name = plugin_info['name']
			icon_pixbuf = self.cardapio.icon_helper.get_icon_pixbuf(plugin_info['category icon'], icon_size, 'package-x-generic')

			if is_required : title = '<b>%s</b>' % name
			self.plugin_tree_model.append([basename, name, name, is_active, is_core, not is_required, icon_pixbuf])

		self.update_plugin_description()
		self.dialog.show()

		self.is_change_handler_blocked = False


	def hide(self, *dummy):
		"""
		Hides the Options Dialog
		"""

		self.dialog.hide()
		self.cardapio.save()

		return True


	def set_widget_from_option(self, widget_str, option_str):
		"""
		Set the value of the widget named 'widget_str' to 'option_str'
		"""

		widget = self.get_widget(widget_str)

		if type(widget) is gtk.Entry:
			widget.set_text(self.cardapio.settings[option_str])

		elif type(widget) is gtk.CheckButton:
			widget.set_active(self.cardapio.settings[option_str])

		else:
			logging.error('Widget %s (%s) was not written' % (widget_str, type(widget)))


	def on_grab_new_shortcut_toggled(self, button):
		"""
		Starts/stops listening for new keybindings
		"""

		if button.get_active():

			self.cardapio.unset_keybinding()

			self.key_grab_handler = self.dialog.connect('key-press-event', self.on_new_keybinding_press)
			self.get_widget('OptionGrabKeybinding').set_label(_('Recording...'))

		else:

			self.dialog.disconnect(self.key_grab_handler)
			self.get_widget('OptionGrabKeybinding').set_label(_('Grab new shortcut'))
			self.on_options_changed()


	def on_new_keybinding_press(self, widget, event):
		"""
		Handler for then the options window is listening for a new keybinding.

		Behavior:
		- All keys combos are valid, except pure "Esc" (which cancels the
		  operation), and pure "Del" or pure "Backspace" (both of which clear
		  keybinding).
		- When the user presses a non-special key (such as "space" or "a"), we
		  stop listening and save the combo.
		- If a non-standard key combo is desired (such as pure "Super_L"), the
		  user must untoggle the keybinding options button with the mouse.
		"""

		main_key = event.keyval
		main_key_string = gtk.gdk.keyval_name(main_key)

		modifier_key = event.state
		modifier_string = u''

		if modifier_key & gtk.gdk.SHIFT_MASK   : modifier_string += '<shift>'
		if modifier_key & gtk.gdk.CONTROL_MASK : modifier_string += '<control>'
		if modifier_key & gtk.gdk.SUPER_MASK   : modifier_string += '<super>'
		if modifier_key & gtk.gdk.HYPER_MASK   : modifier_string += '<hyper>'
		if modifier_key & gtk.gdk.META_MASK    : modifier_string += '<meta>'
		if modifier_key & gtk.gdk.MOD1_MASK    : modifier_string += '<alt>'

		# TODO: Are these needed? How to resolve the case where Super = Mod4, causing
		# both keys to be detected at the same time?
		# TODO: Why is MOD2 always ON no matter what?! (on one of my computers)
		#if modifier_key & gtk.gdk.MOD2_MASK    : modifier_string += '<mod2>'
		#if modifier_key & gtk.gdk.MOD3_MASK    : modifier_string += '<mod3>'
		#if modifier_key & gtk.gdk.MOD4_MASK    : modifier_string += '<mod4>'
		#if modifier_key & gtk.gdk.MOD5_MASK    : modifier_string += '<mod5>'

		shortcut_string = modifier_string + main_key_string

		# cancel on "Escape"
		if main_key == gtk.keysyms.Escape and not modifier_string:
			self.get_widget('OptionKeybinding').set_text(self.cardapio.settings['keybinding'])
			self.get_widget('OptionGrabKeybinding').set_active(False)
			return True

		# clear on "BackSpace" or "Delete"
		if main_key in (gtk.keysyms.BackSpace, gtk.keysyms.Delete) and not modifier_string:
			self.get_widget('OptionKeybinding').set_text('')
			self.get_widget('OptionGrabKeybinding').set_active(False)
			return True

		if main_key_string:
			self.get_widget('OptionKeybinding').set_text(shortcut_string)

			if main_key not in (
					gtk.keysyms.Shift_L, gtk.keysyms.Shift_R, gtk.keysyms.Shift_Lock,
					gtk.keysyms.Control_L, gtk.keysyms.Control_R,
					gtk.keysyms.Super_L, gtk.keysyms.Super_R,
					gtk.keysyms.Hyper_L, gtk.keysyms.Hyper_R,
					gtk.keysyms.Meta_L, gtk.keysyms.Meta_R,
					gtk.keysyms.Alt_L, gtk.keysyms.Alt_R, gtk.keysyms.Mode_switch,
					# TODO: what else?
					#gtk.keysyms.ISO_Level3_Shift, gtk.keysyms.ISO_Group_Shift, 
					):
				self.get_widget('OptionGrabKeybinding').set_active(False)

		return True


	def on_options_changed(self, *dummy):
		"""
		Updates Cardapio's options when the user alters them in the Options
		Dialog
		"""

		if self.is_change_handler_blocked: return

		self.cardapio.settings['keybinding']               = self.get_widget('OptionKeybinding').get_text()
		self.cardapio.settings['applet label']             = self.get_widget('OptionAppletLabel').get_text()
		self.cardapio.settings['applet icon']              = self.get_widget('OptionAppletIcon').get_text()
		self.cardapio.settings['show session buttons']     = self.get_widget('OptionSessionButtons').get_active()
		self.cardapio.settings['keep search results']      = self.get_widget('OptionKeepResults').get_active()
		self.cardapio.settings['open on hover']            = self.get_widget('OptionOpenOnHover').get_active()
		self.cardapio.settings['open categories on hover'] = self.get_widget('OptionOpenCategoriesOnHover').get_active()
		self.cardapio.settings['mini mode']                = self.get_widget('OptionMiniMode').get_active() 

		self.cardapio.apply_settings()


	def update_plugin_description(self, *dummy):
		"""
		Writes information about the currently-selected plugin on the GUI
		"""

		model, iter_ = self.get_widget('PluginTreeView').get_selection().get_selected()

		if iter_ is None:
			is_core = True
			plugin_info = {'name': '', 'version': '', 'author': '', 'description': ''}

		else:
			is_core  = self.plugin_tree_model.get_value(iter_, 4)
			basename = self.plugin_tree_model.get_value(iter_, 0)
			plugin_info = self.cardapio.get_plugin_info(basename)

		description = _('<b>Plugin:</b> %(name)s %(version)s\n<b>Author:</b> %(author)s\n<b>Description:</b> %(description)s') % plugin_info
		if not is_core  : description += '\n<small>(' + _('This is a community-supported plugin') + ')</small>'

		label = self.get_widget('OptionPluginInfo')
		dummy, dummy, width, dummy = label.get_allocation()
		label.set_markup(description)
		label.set_line_wrap(True)

		# make sure the label doesn't resize the window!
		if width > 1:
			label.set_size_request(width - self.scrollbar_width - 20, -1)

		# HACK: The -20 is a hack because some themes add extra padding that I
		# need to account for. Since I don't know where that padding is comming
		# from, I just enter a value (20px) that is larger than I assume any
		# theme would ever use.


	def apply_plugins_from_option_window(self, *dummy):
		"""
		Read plugin settings from the option window
		"""

		self.cardapio.settings['active plugins'] = []
		iter_ = self.plugin_tree_model.get_iter_first()

		while iter_ is not None:

			if self.plugin_tree_model.get_value(iter_, 3):
				self.cardapio.settings['active plugins'].append(self.plugin_tree_model.get_value(iter_, 0))

			iter_ = self.plugin_tree_model.iter_next(iter_)

		self.cardapio.schedule_rebuild(reactivate_plugins = True)


	def on_plugin_state_toggled(self, cell, path):
		"""
		Believe it or not, GTK requires you to manually tell the checkbuttons
		that reside within a tree to toggle when the user clicks on them.
		This function does that.
		"""

		iter_ = self.plugin_tree_model.get_iter(path)
		basename = self.plugin_tree_model.get_value(iter_, 0)

		if basename in self.cardapio.required_plugins: return

		self.plugin_tree_model.set_value(iter_, 3, not cell.get_active())
		self.apply_plugins_from_option_window()


	def on_mini_mode_button_toggled(self, widget):
		"""
		Handler for the minimode checkbox in the preferences window
		"""

		if self.is_change_handler_blocked: return

		self.cardapio.settings['mini mode'] = self.get_widget('OptionMiniMode').get_active()
		self.cardapio.toggle_mini_mode_ui()
		return True


