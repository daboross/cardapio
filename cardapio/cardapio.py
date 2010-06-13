#!/usr/bin/env python
#
#    Cardapio is an alternative Gnome menu applet, launcher, and much more!
#    Copyright (C) 2010 Thiago Teixeira
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

# Before version 1.0:
# TODO: make apps draggable to make shortcuts elsewhere, such as desktop or docky

# After version 1.0:
# TODO: make "places" use custom icons
# TODO: fix shift-tab from first app widget
# TODO: alt-1, alt-2, ..., alt-9, alt-0 should activate categories
# TODO: add mount points to "places", allow ejecting from context menu
# TODO: multiple columns when window is wide enough (like gnome-control-center)
# TODO: slash "/" should navigate inside folders, Esc pops out
# TODO: add "most recent" and "most frequent" with a zeitgeist plugin
# TODO: search results have context menu with "Open with...", "Show parent folder", and so on.
# TODO: figure out if tracker can sort the results by relevancy
# plus other TODO's elsewhere in the code...


try:
	import os
	import re
	import sys
	import gtk
	import gio
	import glib
	import json
	import time
	import gmenu
	import locale
	import urllib2
	import gettext
	import logging
	import commands
	import keybinder
	import subprocess
	import gnomeapplet
	import dbus, dbus.service
	from xdg import BaseDirectory, DesktopEntry
	from dbus.mainloop.glib import DBusGMainLoop
	from distutils.sysconfig import get_python_lib

except Exception, exception:
	print(exception)
	sys.exit(1)

# set up translations

APP = 'cardapio'
DIR = os.path.join(os.path.dirname(__file__), 'locale')

locale.setlocale(locale.LC_ALL, '')
gettext.bindtextdomain(APP, DIR)

if hasattr(gettext, 'bind_textdomain_codeset'):
    gettext.bind_textdomain_codeset(APP, 'UTF-8')

gettext.textdomain(APP)
_ = gettext.gettext

# hack for making translations work with ui files
import gtk.glade
gtk.glade.bindtextdomain(APP, DIR)
gtk.glade.textdomain(APP)


class Cardapio(dbus.service.Object):

	distro_name = commands.getoutput('lsb_release -is')

	min_visibility_toggle_interval = 0.010 # seconds (this is a bit of a hack to fix some focus problems)

	bus_name_str = 'org.varal.Cardapio'
	bus_obj_str  = '/org/varal/Cardapio'

	version = '0.9.97'

	def __init__(self, hidden = False, panel_applet = None, panel_button = None):

		logging.basicConfig(filename = '/tmp/cardapio.log', level = logging.DEBUG)
		logging.info('----------------- Cardapio launched -----------------')

		self.read_config_file()

		self.user_home_folder = os.path.expanduser('~')

		self.panel_applet = panel_applet
		self.panel_button = panel_button
		self.auto_toggled_sidebar_button = False
		self.last_visibility_toggle = 0

		self.visible                   = False
		self.app_list                  = []
		self.section_list              = {}
		self.selected_section          = None
		self.no_results_to_show        = False
		self.previously_focused_widget = None
		self.focus_out_blocked         = False
		self.app_clicked               = None
		self.keybinding                = None
		self.search_timer_local        = None
		self.search_timer_remote       = None
		self.plugin_database           = {}
		self.active_plugin_instances   = []

		self.app_tree = gmenu.lookup_tree('applications.menu')
		self.sys_tree = gmenu.lookup_tree('settings.menu')
		self.app_tree.add_monitor(self.on_menu_data_changed)
		self.sys_tree.add_monitor(self.on_menu_data_changed)

		# TODO: internationalize these
		self.exec_pattern = re.compile("^(.*?)\s+\%[a-zA-Z]$")
		self.sanitize_query_pattern = re.compile("[^a-zA-Z0-9]")

		self.package_root = ''
		if __package__ is not None:
			self.package_root = __package__ + '.'

		self.setup_dbus()
		self.setup_base_ui() # must be the first ui-related method to be called
		self.build_ui() 
		self.build_plugin_database() 
		self.setup_ui_from_all_settings() 
		self.activate_plugins_from_settings()

		self.schedule_search_with_plugins('')

		if not hidden: self.show()

		# this is useful so that the user can edit the config file on first-run 
		# without need to quit cardapio first:
		self.save_config_file()


	def quit(self, *dummy):

		self.save_config_file()
		gtk.main_quit()


	def setup_dbus(self):

		DBusGMainLoop(set_as_default=True)
		self.bus = dbus.SessionBus()
		dbus.service.Object.__init__(self, self.bus, Cardapio.bus_obj_str)

	
	def get_plugin_class(self, basename):

		package = '%splugins.%s' % (self.package_root, basename)
		try:
			plugin_module = __import__(package, fromlist = 'CardapioPlugin', level = -1)
		except:
			return 'Could not find the plugin module'

		plugin_class = plugin_module.CardapioPlugin

		if plugin_class.plugin_api_version != CardapioPluginInterface.plugin_api_version: 
			return 'Incorrect API version'

		return plugin_class


	def build_plugin_database(self):

		self.plugin_database = {}
		plugin_dirs = [
			os.path.join(os.path.dirname(__file__), 'plugins'), 
			os.path.join(DesktopEntry.xdg_config_home, 'Cardapio', 'plugins')
			]

		for plugin_dir in plugin_dirs:

			for root, dir_, files in os.walk(plugin_dir):

				for file_ in files:

					if len(file_) > 3 and file_[-3:] == '.py' and file_[0] != '_':

						basename = file_[:-3]

						plugin_class = self.get_plugin_class(basename)
						if type(plugin_class) is str: continue

						self.plugin_database[basename] = {
							'name' : plugin_class.name,
							'author' : plugin_class.author,
							'description' : plugin_class.description,
							'category name' : plugin_class.category_name,
							'category icon' : plugin_class.category_icon,
							'hide from sidebar' : plugin_class.hide_from_sidebar,
							}


	def activate_plugins_from_settings(self):

		for plugin in self.active_plugin_instances:
			del(plugin)

		self.active_plugin_instances = []

		for basename in self.settings['active plugins']:

			basename = str(basename)

			plugin_class = self.get_plugin_class(basename)
			if type(plugin_class) is str: 
				logging.error('[plugin: %s] %s' % (basename, plugin_class))
				self.settings['active plugins'].remove(basename)
				continue

			plugin = plugin_class(self.settings, self.write_to_plugin_log, self.handle_search_result, self.handle_search_error)

			if not plugin.loaded:
				self.write_to_plugin_log(plugin, 'Plugin did not load properly')
				continue

			section_slab, section_contents = self.add_plugin_slab(plugin)

			plugin.basename         = basename
			plugin.section_slab     = section_slab
			plugin.section_contents = plugin.section_slab.get_children()[0].get_children()[0]

			self.active_plugin_instances.append(plugin)


	def write_to_plugin_log(self, plugin, text, is_error = False, is_warning = False):

		if is_error: 
			write = logging.error

		elif is_warning: 
			write = logging.warning

		else:
			write = logging.debug

		write('[%s] %s'  % (plugin.name, text))


	def on_all_sections_sidebar_button_clicked(self, widget):

		if self.auto_toggled_sidebar_button:
			self.auto_toggled_sidebar_button = False
			return True

		if self.selected_section is None:
			self.clear_search_entry()
			widget.set_sensitive(False)

		else:
			self.show_all_nonempty_sections()


	def on_sidebar_button_clicked(self, widget, section_slab):

		if self.auto_toggled_sidebar_button:
			self.auto_toggled_sidebar_button = False
			return True

		if self.selected_section == section_slab:
			self.selected_section = None # necessary!
			self.show_all_nonempty_sections()
			return True

		self.show_lone_section(section_slab)


	def get_config_file(self, mode):

		config_folder_path = os.path.join(DesktopEntry.xdg_config_home, 'Cardapio')

		if not os.path.exists(config_folder_path): 
			os.mkdir(config_folder_path)

		elif not os.path.isdir(config_folder_path):
			print(_('Error! Path "%s" already exists!') % config_folder_path)
			sys.exit(1)

		config_file_path = os.path.join(DesktopEntry.xdg_config_home, 'Cardapio', 'config.ini')

		if not os.path.exists(config_file_path):
			open(config_file_path, 'w+')

		elif not os.path.isfile(config_file_path):
			print(_('Error! Path "%s" already exists!') % config_file_path)
			sys.exit(1)

		return open(config_file_path, mode)


	def read_config_file(self):

		config_file = self.get_config_file('r')

		self.settings = {}
		s = {}

		try: 
			s = json.load(config_file)

		except Exception, exception:
			logging.warning('Could not read config file:')
			logging.warning(exception)

		finally: 
			config_file.close()

		self.settings['cardapio version'] = self.version

		self.read_config_option(s, 'window size'                , None                     ) # format: [px, px]
		self.read_config_option(s, 'splitter position'          , 0                        ) # format: [px, px]
		self.read_config_option(s, 'show session buttons'       , False                    ) # bool
		self.read_config_option(s, 'min search string length'   , 3                        ) # characters
		self.read_config_option(s, 'menu rebuild delay'         , 10                       , force_update_from_version = [0,9,96]) # seconds
		self.read_config_option(s, 'search results limit'       , 5                        ) # results
		self.read_config_option(s, 'local search update delay'  , 100                      , force_update_from_version = [0,9,96]) # msec
		self.read_config_option(s, 'remote search update delay' , 250                      , force_update_from_version = [0,9,96]) # msec
		self.read_config_option(s, 'keybinding'                 , '<Super>space'           ) # the user should use gtk.accelerator_parse('<Super>space') to see if the string is correct!
		self.read_config_option(s, 'applet label'               , Cardapio.distro_name     ) # string
		self.read_config_option(s, 'applet icon'                , 'start-here'             , override_empty_str = True) # string (either a path to the icon, or an icon name)
		self.read_config_option(s, 'pinned items'               , []                       ) # URIs
		self.read_config_option(s, 'active plugins'             , ['tracker', 'google']    ) # filenames


	def read_config_option(self, user_settings, key, val, override_empty_str = False, force_update_from_version = None):

		if key in user_settings:
			if override_empty_str and len(user_settings[key]) == 0:
				self.settings[key] = val
			else:
				self.settings[key] = user_settings[key]
		else: 
			self.settings[key] = val

		if force_update_from_version is not None:

			if 'cardapio version' in user_settings:
				user_version = [int(i) for i in user_settings['cardapio version'].split('.')]

			else:
				user_version = 0

			if user_version < force_update_from_version:

				self.settings[key] = val


	def save_config_file(self):

		if self.get_object('MainSplitter').get_property('position_set'):
			self.settings['splitter position'] = self.get_object('MainSplitter').get_position()

		else:
			self.settings['splitter position'] = 0

		config_file = self.get_config_file('w')
		json.dump(self.settings, config_file, sort_keys = True, indent = 4)


	def setup_base_ui(self):

		self.rebuild_timer = None

		cardapio_path = os.path.dirname(__file__)
		self.uifile = os.path.join(cardapio_path, 'cardapio.ui')

		self.builder = gtk.Builder()
		self.builder.set_translation_domain(APP)
		self.builder.add_from_file(self.uifile)
		self.builder.connect_signals(self)

		self.get_object = self.builder.get_object
		self.window             = self.get_object('MainWindow')
		self.message_window     = self.get_object('MessageWindow')
		self.about_dialog       = self.get_object('AboutDialog')
		self.options_dialog     = self.get_object('OptionsDialog')
		self.application_pane   = self.get_object('ApplicationPane')
		self.category_pane      = self.get_object('CategoryPane')
		self.sideapp_pane       = self.get_object('SideappPane')
		self.search_entry       = self.get_object('SearchEntry')
		self.scrolled_window    = self.get_object('ScrolledWindow')
		self.scroll_adjustment  = self.scrolled_window.get_vadjustment()
		self.session_pane       = self.get_object('SessionPane')
		self.left_session_pane  = self.get_object('LeftSessionPane')
		self.right_session_pane = self.get_object('RightSessionPane')
		self.context_menu       = self.get_object('CardapioContextMenu')
		self.app_context_menu   = self.get_object('AppContextMenu')
		self.pin_menuitem       = self.get_object('PinMenuItem')
		self.unpin_menuitem     = self.get_object('UnpinMenuItem')
		self.plugin_tree_model  = self.get_object('PluginListstore')

		self.icon_theme = gtk.icon_theme_get_default()
		self.icon_theme.connect('changed', self.on_icon_theme_changed)
		self.icon_size_app = gtk.ICON_SIZE_LARGE_TOOLBAR
		self.icon_size_category = gtk.ICON_SIZE_MENU

		# make sure buttons have icons!
		self.gtk_settings = gtk.settings_get_default()
		self.gtk_settings.set_property('gtk-button-images', True)
		self.gtk_settings.connect('notify', self.on_gtk_settings_changed)

		self.window.set_keep_above(True)

		self.get_object('MarginLeft').realize()
		self.get_object('MarginRight').realize()
		self.get_object('MarginTop').realize()
		self.get_object('MarginTopLeft').realize()
		self.get_object('MarginTopRight').realize()
		self.get_object('MarginBottom').realize()
		self.get_object('MarginBottomLeft').realize()
		self.get_object('MarginBottomRight').realize()
		self.get_object('MarginLeft').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.LEFT_SIDE))
		self.get_object('MarginRight').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.RIGHT_SIDE))
		self.get_object('MarginTop').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.TOP_SIDE))
		self.get_object('MarginTopLeft').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.TOP_LEFT_CORNER))
		self.get_object('MarginTopRight').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.TOP_RIGHT_CORNER))
		self.get_object('MarginBottom').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.BOTTOM_SIDE))
		self.get_object('MarginBottomLeft').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.BOTTOM_LEFT_CORNER))
		self.get_object('MarginBottomRight').window.set_cursor(gtk.gdk.Cursor(gtk.gdk.BOTTOM_RIGHT_CORNER))

		self.context_menu_xml = '''
			<popup name="button3">
				<menuitem name="Item 1" verb="Properties" label="%s" pixtype="stock" pixname="gtk-properties"/>
				<menuitem name="Item 2" verb="Edit" label="%s" pixtype="stock" pixname="gtk-edit"/>
				<menuitem name="Item 3" verb="AboutCardapio" label="%s" pixtype="stock" pixname="gtk-about"/>
				<separator />
				<menuitem name="Item 4" verb="AboutGnome" label="%s" pixtype="none"/>
				<menuitem name="Item 5" verb="AboutDistro" label="%s" pixtype="none"/>
			</popup>
			''' % (
				_('_Properties'), 
				_('_Edit Menus'), 
				_('_About Cardapio'), 
				_('_About Gnome'), 
				_('_About %(distro_name)s') % {'distro_name' : Cardapio.distro_name}
			)

		self.context_menu_verbs = [
			('Properties', self.open_options_dialog),
			('Edit', self.launch_edit_app),
			('AboutCardapio', self.open_about_dialog),
			('AboutGnome', self.open_about_dialog),
			('AboutDistro', self.open_about_dialog)
		]

		if self.panel_applet is not None:
			self.panel_applet.connect('destroy', self.quit)


	def get_best_icon_size(self):

		panel = self.panel_button.get_toplevel().window

		if panel is None: 
			return gtk.icon_size_lookup(gtk.ICON_SIZE_LARGE_TOOLBAR)[0]

		panel_width, panel_height = panel.get_size()
		orientation = self.panel_applet.get_orient()

		if orientation == gnomeapplet.ORIENT_DOWN or orientation == gnomeapplet.ORIENT_UP:
			panel_size = panel_height

		else:
			panel_size = panel_width

		# "snap" the icon size to the closest stock icon size
		for icon_size in range(1,7):

			icon_size_pixels = gtk.icon_size_lookup(icon_size)[0]

			if abs(icon_size_pixels - panel_size) < 3:
				return icon_size_pixels

		# if no stock icon size if close enough, then use the panel size
		return panel_size


	def setup_panel_button(self):

		self.panel_button.set_label(self.settings['applet label'])
		button_icon = self.get_icon(self.settings['applet icon'], self.get_best_icon_size(), 'distributor-logo')
		self.panel_button.set_image(button_icon)


	def setup_ui_from_all_settings(self):

		self.setup_ui_from_gui_settings()

		if self.settings['splitter position'] > 0:
			self.get_object('MainSplitter').set_position(self.settings['splitter position'])


	def setup_ui_from_gui_settings(self):

		if self.keybinding is not None:
			keybinder.unbind(self.keybinding)

		self.keybinding = self.settings['keybinding']
		keybinder.bind(self.keybinding, self.show_hide)

		if self.panel_button is not None:
			self.setup_panel_button()

		if self.settings['show session buttons']:
			self.session_pane.show()
		else:
			self.session_pane.hide()


	def build_ui(self):

		self.prepare_colors()

		self.clear_pane(self.application_pane)
		self.clear_pane(self.category_pane)
		self.clear_pane(self.sideapp_pane)
		self.clear_pane(self.left_session_pane)
		self.clear_pane(self.right_session_pane)

		self.section_list = {}
		self.app_list = []

		button = self.add_sidebar_button(_('All'), None, self.category_pane, tooltip = _('Show all categories'), append = False)
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_sections_sidebar_button = button 
		self.set_sidebar_button_active(button, True)
		self.all_sections_sidebar_button.set_sensitive(False)

		self.no_results_slab, dummy, self.no_results_label = self.add_application_section('Dummy text')
		self.hide_no_results_text()

		if self.panel_applet is None:
			self.get_object('LabelAppletLabel').hide()
			self.get_object('OptionAppletLabel').hide()
			self.get_object('LabelAppletIcon').hide()
			self.get_object('OptionAppletIcon').hide()

		# slabs that should go *before* regular application slabs
		self.add_favorites_slab()
		self.add_places_slab()
		self.add_help_slab()

		self.build_applications_list()

		# slabs that should go *after* regular application slabs
		self.add_session_slab()
		self.add_system_slab()

		self.build_favorites_list()
		self.build_places_list()
		self.build_session_list()
		self.build_system_list()
		self.build_help_list()

		self.set_message_window_visible(False)


	def rebuild_ui(self, show_message = False):

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)
			self.rebuild_timer = None

		if show_message:
			self.set_message_window_visible(True)

		glib.idle_add(self.build_ui)


	def open_about_dialog(self, widget, verb):

		if verb == 'AboutCardapio':
			self.about_dialog.show()

		elif verb == 'AboutGnome':
			self.launch_raw('gnome-about')

		elif verb == 'AboutDistro':
			self.launch_raw('yelp ghelp:about-%s' % Cardapio.distro_name.lower())
			# i'm assuming this is the pattern for all distros...


	def on_about_dialog_close(self, widget, response = None):

		self.about_dialog.hide()


	def open_options_dialog(self, *dummy):

		self.get_object('OptionKeybinding').set_text(self.settings['keybinding'])
		self.get_object('OptionAppletLabel').set_text(self.settings['applet label'])
		self.get_object('OptionAppletIcon').set_text(self.settings['applet icon'])
		self.get_object('OptionSessionButtons').set_active(self.settings['show session buttons'])

		self.plugin_tree_model.clear()

		# place active plugins at the top of the list, in order
		plugin_list = []
		plugin_list += [p.basename for p in self.active_plugin_instances]
		plugin_list += [basename for basename in self.plugin_database if basename not in plugin_list]

		for basename in plugin_list:

			active = (basename in self.settings['active plugins'])
			plugin_info = self.plugin_database[basename]

			title = '<big><b>%(plugin_name)s</b></big>\n<i>by %(plugin_author)s</i>\n%(plugin_description)s' % {
					'plugin_name' : plugin_info['name'],
					'plugin_author': plugin_info['author'],
					'plugin_description': plugin_info['description'],
					}

			self.plugin_tree_model.append([basename, active, title])

		self.options_dialog.show()

	
	def close_options_dialog(self, widget, response = None):

		self.options_dialog.hide()


	def on_options_changed(self, *dummy):

		self.settings['keybinding'] = self.get_object('OptionKeybinding').get_text()
		self.settings['applet label'] = self.get_object('OptionAppletLabel').get_text()
		self.settings['applet icon'] = self.get_object('OptionAppletIcon').get_text()
		self.settings['show session buttons'] = self.get_object('OptionSessionButtons').get_active()
		self.setup_ui_from_gui_settings()


	def on_plugin_apply_clicked(self, widget):

		self.settings['active plugins'] = []
		iter_ = self.plugin_tree_model.get_iter_first()

		while iter_ is not None:

			if self.plugin_tree_model.get_value(iter_, 1):
				self.settings['active plugins'].append(self.plugin_tree_model.get_value(iter_, 0))

			iter_ = self.plugin_tree_model.iter_next(iter_)

		self.activate_plugins_from_settings()


	def on_plugin_state_toggled(self, cell, path):

		iter_ = self.plugin_tree_model.get_iter(path)
		self.plugin_tree_model.set_value(iter_, 1, not cell.get_active())	


	def on_mainwindow_destroy(self, widget):

		self.quit()


	def on_mainwindow_button_pressed(self, widget, event):

		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
			self.block_focus_out_event()
			self.context_menu.popup(None, None, None, event.button, event.time)


	def start_resize(self, widget, event):

		window_x, window_y = self.window.get_position()
		x = event.x_root - window_x
		y = event.y_root - window_y
		window_width, window_height = self.window.get_size()
		resize_margin = 10
		
		if x < resize_margin:

			if y < resize_margin:
				edge = gtk.gdk.WINDOW_EDGE_NORTH_WEST

			elif y > window_height - resize_margin:
				edge = gtk.gdk.WINDOW_EDGE_SOUTH_WEST

			else:
				edge = gtk.gdk.WINDOW_EDGE_WEST

		elif x > window_width - resize_margin:

			if y < resize_margin:
				edge = gtk.gdk.WINDOW_EDGE_NORTH_EAST

			elif y > window_height - resize_margin:
				edge = gtk.gdk.WINDOW_EDGE_SOUTH_EAST

			else:
				edge = gtk.gdk.WINDOW_EDGE_EAST

		else:
			if y < resize_margin:
				edge = gtk.gdk.WINDOW_EDGE_NORTH

			else:
				edge = gtk.gdk.WINDOW_EDGE_SOUTH
		
		x = int(event.x_root)
		y = int(event.y_root)

		self.block_focus_out_event()
		self.window.window.begin_resize_drag(edge, event.button, x, y, event.time)


	def block_focus_out_event(self):

		self.window.handler_block_by_func(self.on_mainwindow_focus_out)
		self.focus_out_blocked = True


	def unblock_focus_out_event(self, *dummy):

		if self.focus_out_blocked:
			self.window.handler_unblock_by_func(self.on_mainwindow_focus_out)
			self.focus_out_blocked = False


	def on_mainwindow_key_pressed(self, widget, event):

		# make sure we aren't already at the search_entry, nor are we going
		# there due to this keypress

		if self.window.get_focus() != self.search_entry:
			self.previously_focused_widget = self.window.get_focus()


	def on_mainwindow_after_key_pressed(self, widget, event):

		w = self.window.get_focus()

		if w != self.search_entry and w == self.previously_focused_widget:

			if event.is_modifier: return

			self.previously_focused_widget = None
			self.window.set_focus(self.search_entry)
			self.search_entry.emit('key-press-event', event)


	def on_mainwindow_focus_out(self, widget, event):

		if self.panel_applet is None:
			self.hide()
			return

		x, y, dummy = self.panel_applet.window.get_pointer()
		dummy, dummy, w, h = self.panel_applet.get_allocation()

		# make sure clicking the applet button doesn't cause a focus-out event
		if (0 <= x <= w and 0 <= y <= h): 
			return

		# make sure resizing doesn't cause a focus-out event
		window_x, window_y = self.window.window.get_origin()
		window_w, window_h = self.window.window.get_size()

		if 0 <= x <= window_w and 0 <= y <= window_h:

			mask = widget.window.get_pointer()[2]

			if (
				gtk.gdk.BUTTON1_MASK & mask == gtk.gdk.BUTTON1_MASK or
				gtk.gdk.BUTTON2_MASK & mask == gtk.gdk.BUTTON2_MASK or
				gtk.gdk.BUTTON3_MASK & mask == gtk.gdk.BUTTON3_MASK or
				gtk.gdk.BUTTON4_MASK & mask == gtk.gdk.BUTTON4_MASK or
				gtk.gdk.BUTTON5_MASK & mask == gtk.gdk.BUTTON5_MASK 
				):
				return

		self.hide()


	def on_mainwindow_delete_event(self, widget, event):

		if self.panel_applet:
			# keep window alive if in panel mode
			return True


	def on_mainwindow_configure_event(self, widget, event):

		self.save_dimensions()


	def on_icon_theme_changed(self, icon_theme):

		self.schedule_rebuild()


	def on_gtk_settings_changed(self, gobj, property_changed):

		if property_changed.name == 'gtk-color-scheme' or property_changed.name == 'gtk-theme-name':
			self.prepare_colors()
			self.schedule_rebuild()


	def schedule_rebuild(self):

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)

		self.rebuild_timer = glib.timeout_add_seconds(self.settings['menu rebuild delay'], self.rebuild_ui)


	def on_menu_data_changed(self, tree):

		self.schedule_rebuild()


	def on_searchentry_icon_pressed(self, widget, iconpos, event):

		if self.is_searchfield_empty():
			self.show_all_nonempty_sections()

		else:
			self.clear_search_entry()


	def on_searchentry_changed(self, widget):

		self.no_results_to_show = True
		text = self.search_entry.get_text().strip()

		self.search_menus(text)
		self.schedule_search_with_plugins(text)

		if len(text) == 0:
			#self.no_results_to_show = False

			self.hide_all_transitory_sections(fully_hide = True)
			return

		else:
			self.all_sections_sidebar_button.set_sensitive(True)

		if len(text) < self.settings['min search string length']:

			for plugin in self.active_plugin_instances:
				if plugin.hide_from_sidebar:
					self.set_section_is_empty(plugin.section_slab)
					plugin.section_slab.hide()


	def search_menus(self, text):

		text = text.lower()

		for sec in self.section_list:
			self.set_section_is_empty(sec)

		for app in self.app_list:

			if app['name'].find(text) == -1:
				app['button'].hide()
			else:
				app['button'].show()
				self.set_section_has_entries(app['section'])
				self.no_results_to_show = False

		if self.selected_section is None:
			self.show_all_nonempty_sections()
		else:
			self.consider_showing_no_results_text()


	def schedule_search_with_plugins(self, text):

		if self.search_timer_local is not None:
			glib.source_remove(self.search_timer_local)

		if self.search_timer_remote is not None:
			glib.source_remove(self.search_timer_remote)

		delay_type = 'local search update delay'
		delay = self.settings[delay_type]
		self.search_timer_local = glib.timeout_add(delay, self.search_with_plugins, text, delay_type)

		delay_type = 'remote search update delay'
		delay = self.settings[delay_type]
		self.search_timer_remote = glib.timeout_add(delay, self.search_with_plugins, text, delay_type)

		self.search_with_plugins(text, None)


	def search_with_plugins(self, text, delay_type):

		if delay_type == 'local search update delay':
			glib.source_remove(self.search_timer_local)
			self.search_timer_local = None

		elif delay_type == 'remote search update delay':
			glib.source_remove(self.search_timer_remote)
			self.search_timer_remote = None

		for plugin in self.active_plugin_instances:
			if plugin.search_delay_type == delay_type:
				if not plugin.hide_from_sidebar or len(text) >= self.settings['min search string length']:
					#if plugin.is_running: plugin.cancel()
					plugin.is_running = True
					plugin.search(text)

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def handle_search_error(self, plugin, text):

		plugin.is_running = False
		self.write_to_plugin_log(plugin, text, is_error = True)
		self.handle_search_result(plugin, [])


	def handle_search_result(self, plugin, results):

		plugin.is_running = False

		if plugin.hide_from_sidebar and len(self.search_entry.get_text()) < self.settings['min search string length']:

			# Handle the case where user presses backspace *very* quickly, and the
			# search starts when len(text) > min_search_string_length, but after
			# search_update_delay milliseconds this method is called while the
			# search entry now has len(text) < min_search_string_length

			# Anyways, it's hard to explain, but suffice to say it's a race
			# condition and we handle it here.

			self.set_section_is_empty(plugin.section_slab)
			plugin.section_slab.hide()
			return

		gtk.gdk.threads_enter()

		container = plugin.section_contents.parent
		if container is None:
			# plugin was deactivated while waiting for search result
			return

		container.remove(plugin.section_contents)
		plugin.section_contents = gtk.VBox()
		container.add(plugin.section_contents)

		for result in results:

			dummy, canonical_path = urllib2.splittype(result['xdg uri'])
			parent_name, child_name = os.path.split(canonical_path)

			icon_name = result['icon name'].replace('/', '-')
			if not self.icon_theme.has_icon(icon_name):
				icon_name = 'text-x-generic'

			button = self.add_launcher_entry(result['name'], icon_name, plugin.section_contents, 'xdg', result['xdg uri'], tooltip = result['tooltip'])

		if results:

			self.no_results_to_show = False

			plugin.section_contents.show()
			self.set_section_has_entries(plugin.section_slab)

			if self.selected_section is None or self.selected_section == plugin.section_slab:
				plugin.section_slab.show()
				self.hide_no_results_text()

			else:
				self.consider_showing_no_results_text()

		else:

			self.set_section_is_empty(plugin.section_slab)

			if self.selected_section is None or self.selected_section == plugin.section_slab:
				plugin.section_slab.hide()

			self.consider_showing_no_results_text()

		gtk.gdk.threads_leave()


	def is_searchfield_empty(self):

		return (len(self.search_entry.get_text().strip()) == 0)


	def on_searchentry_activate(self, widget):

		for plugin in self.active_plugin_instances:
			if plugin.is_running: plugin.cancel()

		if self.is_searchfield_empty():
			self.hide_all_transitory_sections()
			return 

		first_app_widget = self.get_first_visible_app()
		if first_app_widget is not None:
			first_app_widget.emit('clicked')

		self.clear_search_entry()


	def on_searchentry_key_pressed(self, widget, event):

		# make Tab go to first result element
		if event.keyval == gtk.gdk.keyval_from_name('Tab'):

			if self.selected_section is not None:

				contents = self.section_list[self.selected_section]['contents']
				visible_children = [c for c in contents.get_children() if c.get_property('visible')]

				if visible_children:
					self.window.set_focus(visible_children[0])

			else:
				first_app_widget = self.get_first_visible_app()
				if first_app_widget is not None: 
					self.window.set_focus(first_app_widget)
				

		elif event.keyval == gtk.gdk.keyval_from_name('Escape'):

			for plugin in self.active_plugin_instances:
				if plugin.is_running: plugin.cancel()

			if not self.is_searchfield_empty():
				self.clear_search_entry()

			elif self.selected_section is not None:
				self.show_all_nonempty_sections()

			else:
				self.hide()

		else: return False
		return True


	def get_first_visible_app(self):

		for slab in self.application_pane.get_children():
			if not slab.get_visible(): continue

			for app in slab.get_children()[0].get_children()[0].get_children():
				if not app.get_visible(): continue

				return app

		return None


	# make Tab go from first result element to text entry widget
	def on_first_button_key_pressed(self, widget, event):

		if event.keyval == gtk.gdk.keyval_from_name('ISO_Left_Tab'):

			self.window.set_focus(self.search_entry)

		else: return False
		return True


	def reposition_window(self, is_message_window = False):

		window_width, window_height = self.window.get_size()
		screen_height = gtk.gdk.screen_height()
		screen_width  = gtk.gdk.screen_width()

		if is_message_window:
			window = self.message_window
			message_width, message_height = self.message_window.get_size()
			offset_x = (window_width - message_width) / 2
			offset_y = (window_height - message_height) / 2

		else:
			window = self.window
			offset_x = offset_y = 0

		if self.panel_applet is None:
			window_x = (screen_width - window_width)/2
			window_y = (screen_height - window_height)/2
			window.move(window_x + offset_x, window_y + offset_y)
			return

		panel = self.panel_button.get_toplevel().window
		panel_x, panel_y = panel.get_origin()
		panel_width, panel_height = panel.get_size()

		applet_x, applet_y, applet_width, applet_height = self.panel_button.get_allocation()
		orientation = self.panel_applet.get_orient()

		# weird:
		# - orient_up    means panel is at the bottom
		# - orient_down  means panel is at the top
		# - orient_left  means panel is at the ritgh
		# - orient_right means panel is at the left

		# top
		if orientation == gnomeapplet.ORIENT_DOWN:
			window_x = panel_x + applet_x
			window_y = panel_y + applet_y + applet_height
			
		# bottom
		elif orientation == gnomeapplet.ORIENT_UP:
			window_x = panel_x + applet_x
			window_y = panel_y + applet_y - window_height

		# left
		elif orientation == gnomeapplet.ORIENT_RIGHT:
			window_x = panel_x + applet_x + applet_width
			window_y = panel_y + applet_y
		
		# right
		elif orientation == gnomeapplet.ORIENT_LEFT:
			window_x = panel_x + applet_x - window_width
			window_y = panel_y + applet_y

		if window_x + window_width > screen_width:
			window_x = screen_width - window_width

		if window_y + window_height > screen_height:
			window_y = screen_height - window_height

		if window_x < 0:
			window_x = 0

		if window_y < 0:
			window_y = 0

		window.move(window_x + offset_x, window_y + offset_y)


	def restore_dimensions(self):

		if self.settings['window size'] is not None: 
			self.window.resize(*self.settings['window size'])


	def save_dimensions(self):

		self.settings['window size'] = self.window.get_size()


	def set_message_window_visible(self, state = True):

		if state == False:
			self.message_window.hide()
			return

		self.reposition_window(is_message_window = True)

		self.message_window.set_keep_above(True)
		self.show_window_on_top(self.message_window)

		# ensure window is rendered immediately
		gtk.gdk.flush()
		while gtk.events_pending():
			gtk.main_iteration()


	def show(self):

		self.auto_toggle_panel_button(True)

		self.restore_dimensions()
		self.reposition_window()
		self.show_window_on_top(self.window)

		self.window.set_focus(self.search_entry)
 		self.scroll_to_top()

		self.visible = True
		self.last_visibility_toggle = time.time()

		if self.rebuild_timer is not None:
			# build the UI *after* showing the window, so the user gets the
			# satisfaction of seeing the window pop up, even if it's incomplete...
			self.rebuild_ui(show_message = True)


	def hide(self):

		self.auto_toggle_panel_button(False)

		self.visible = False
		self.last_visibility_toggle = time.time()

		self.save_dimensions()

		self.window.hide()

		self.clear_search_entry()
		self.show_all_nonempty_sections()


	@dbus.service.method(dbus_interface=bus_name_str, in_signature=None, out_signature=None)
	def show_hide(self):

		if time.time() - self.last_visibility_toggle < Cardapio.min_visibility_toggle_interval:
			return

		if self.visible: self.hide()
		else: self.show()


	def show_window_on_top(self, window):

		window.show_now()

		# for compiz, this must take place twice!!
		window.present_with_time(int(time.time()))
		window.present_with_time(int(time.time()))

		# for metacity, this is required!!
		window.window.focus() 


	def on_panel_button_pressed(self, widget, event):
		# used for the menu only

		if event.type == gtk.gdk.BUTTON_PRESS:

			if event.button == 3:

				widget.emit_stop_by_name('button-press-event')
				self.panel_applet.setup_menu(self.context_menu_xml, self.context_menu_verbs, None)

			if event.button == 2:

				# make sure middle click does nothing, so it can be used to move
				# the applet

				widget.emit_stop_by_name('button-press-event')
				self.hide()


	def on_panel_button_toggled(self, widget, event):

		if event.type == gtk.gdk.BUTTON_PRESS:

			if event.button == 1:

				if self.visible: self.hide()
				else: self.show()

				return True # required! or we get strange focus problems


	def on_panel_size_changed(self, widget, allocation):

		self.panel_applet.handler_block_by_func(self.on_panel_size_changed)
		glib.timeout_add(100, self.setup_panel_button)
		glib.timeout_add(200, self.on_panel_size_change_done) # added this to avoid an infinite loop


	def on_panel_size_change_done(self):

		self.panel_applet.handler_unblock_by_func(self.on_panel_size_changed)
		return False # must return false to cancel the timer


	def panel_change_orientation(self, *dummy):

		orientation = self.panel_applet.get_orient()

		if orientation == gnomeapplet.ORIENT_UP or orientation == gnomeapplet.ORIENT_DOWN:
			self.panel_button.parent.set_child_pack_direction(gtk.PACK_DIRECTION_LTR)
			self.panel_button.child.set_angle(0)
			self.panel_button.child.set_alignment(0, 0.5)

		elif orientation == gnomeapplet.ORIENT_RIGHT:
			self.panel_button.parent.set_child_pack_direction(gtk.PACK_DIRECTION_BTT)
			self.panel_button.child.set_angle(90)
			self.panel_button.child.set_alignment(0.5, 0)

		elif orientation == gnomeapplet.ORIENT_LEFT:
			self.panel_button.parent.set_child_pack_direction(gtk.PACK_DIRECTION_TTB)
			self.panel_button.child.set_angle(270)
			self.panel_button.child.set_alignment(0.5, 0)


	def on_panel_change_background(self, widget, bg_type, color, pixmap):

		self.panel_button.parent.set_style(None)

		clean_style = gtk.RcStyle()
		self.panel_button.parent.modify_style(clean_style)

		if bg_type == gnomeapplet.NO_BACKGROUND:
			# TODO: fix bug where going from "Solid color" back to "None (use
			# system theme)" causes cardapio to keep a "Solid color" background.
			# This means I probably need to reset some theme-related property here,
			# I just don't know what...
			pass

		elif bg_type == gnomeapplet.COLOR_BACKGROUND:
			self.panel_button.parent.modify_bg(gtk.STATE_NORMAL, color)

		else: #if bg_type == gnomeapplet.PIXMAP_BACKGROUND:
			style = self.panel_button.style
			style.bg_pixmap[gtk.STATE_NORMAL] = pixmap
			self.panel_button.parent.set_style(style)


	def auto_toggle_panel_button(self, state):

		if self.panel_applet is not None:

			if state: self.panel_button.select()
			else: self.panel_button.deselect()


	def build_help_list(self):

		items = [
			[
				'gnome-control-center', 
				_('Control Center'), 
				_('The Gnome configuration tool'), 
				'gnome-control-center',
				self.system_section_contents
			],
			[
				'gnome-help', 
				_('Help and Support'), 
				_('Get help with %(distro_name)s') % {'distro_name':Cardapio.distro_name}, 
				'help-contents',
				self.help_section_contents
			],
		]

		for item in items:

			button = self.add_sidebar_button(item[1], item[3], self.sideapp_pane, tooltip = item[2], use_toggle_button = False)
			button.connect('clicked', self.on_raw_button_clicked, item[0])

			button = self.add_launcher_entry(item[1], item[3], item[4], 'raw', item[0], tooltip = item[2], app_list = self.app_list)


	def build_places_list(self):

		button = self.add_launcher_entry(_('Home'), 'user-home', self.places_section_contents, 'xdg', self.user_home_folder, tooltip = _('Open your personal folder'), app_list = self.app_list)
		button = self.add_launcher_entry(_('Computer'), 'computer', self.places_section_contents, 'xdg', 'computer:///', tooltip = _('Browse all local and remote disks and folders accessible from this computer'), app_list = self.app_list)

		xdg_folders_file_path = os.path.join(DesktopEntry.xdg_config_home, 'user-dirs.dirs')
		xdg_folders_file = file(xdg_folders_file_path, 'r')

		for line in xdg_folders_file.readlines():

			res = re.match('\s*XDG_DESKTOP_DIR\s*=\s*"(.+)"', line)
			if res is not None:
				path = res.groups()[0]
				self.add_place(_('Desktop'), path, 'user-desktop')

			# TODO: use this loop to find which folders need special icons 

		xdg_folders_file.close()

		bookmark_file_path = os.path.join(self.user_home_folder, '.gtk-bookmarks')
		bookmark_file = file(bookmark_file_path, 'r')

		for line in bookmark_file.readlines():
			if line.strip(' \n\r\t'):
				name, path = self.get_place_name_and_path(line)
				# TODO: make sure path exists
				# TODO: if path doesn't exist, add gio monitor (could be a removable disk)
				self.add_place(name, path, 'folder')

		bookmark_file.close()

		self.bookmark_monitor = gio.File(bookmark_file_path).monitor_file()  # keep a reference to avoid getting it garbage collected
		self.bookmark_monitor.connect('changed', self.on_bookmark_monitor_changed)

		button = self.add_launcher_entry(_('Trash'), 'user-trash', self.places_section_contents, 'xdg', 'trash:///', tooltip = _('Open the trash'), app_list = self.app_list)


	def on_bookmark_monitor_changed(self, monitor, file, other_file, event):

		if event == gio.FILE_MONITOR_EVENT_CHANGES_DONE_HINT:

			# TODO: make sure this doesn't fire 5 times per change!

			for item in self.places_section_contents.get_children():
				self.places_section_contents.remove(item)

			self.build_places_list()


	def get_folder_name_and_path(self, folder_path):

		path = folder_path.strip(' \n\r\t')

		res = folder_path.split(os.path.sep)
		if res: 
			name = res[-1].strip(' \n\r\t').replace('%20', ' ')
			if name: return name, path

		# TODO: handle remote folders like nautilus does (i.e. '/home on ftp.myserver.net')
		name = path.replace('%20', ' ')	
		return name, path


	def get_place_name_and_path(self, folder_path):

		res = folder_path.split(' ')
		if len(res) > 1: 
			name = ' '.join(res[1:]).strip(' \n\r\t')
			path = res[0]
			return name, path

		return self.get_folder_name_and_path(folder_path)


	def add_place(self, folder_name, folder_path, folder_icon):

		folder_path = os.path.expanduser(folder_path.replace('$HOME', '~')).strip(' \n\r\t')

		dummy, canonical_path = urllib2.splittype(folder_path)
		canonical_path = self.unescape(canonical_path)

		if not urllib2.posixpath.exists(canonical_path): return

		button = self.add_launcher_entry(folder_name, folder_icon, self.places_section_contents, 'xdg', folder_path, tooltip = folder_path, app_list = self.app_list)


	def build_favorites_list(self):

		self.show_section(self.favorites_section_slab, fully_show = True)
		text = self.search_entry.get_text().lower()

		no_results = True 
		
		for app in self.settings['pinned items']:

			button = self.add_launcher_entry(app['name'], app['icon_name'], self.favorites_section_contents, app['type'], app['command'], tooltip = app['tooltip'], app_list = self.app_list)

			if app['name'].lower().find(text) == -1:
				button.hide()
			else:
				button.show()
				self.set_section_has_entries(self.favorites_section_slab)
				self.no_results_to_show = False
				no_results = False

		if no_results:
			self.hide_section(self.favorites_section_slab, fully_hide = True)

		elif self.selected_section is not None and self.selected_section != self.favorites_section_slab:
			self.hide_section(self.favorites_section_slab)


	def build_session_list(self):

		items = [
			[
				_('Lock Screen'),
				_('Protect your computer from unauthorized use'),
				'system-lock-screen',
				'gnome-screensaver-command --lock',
				self.left_session_pane,
			],
			[
				_('Log Out...'),
				_('Log out of this session to log in as a different user'),
				'system-log-out', 
				'gnome-session-save --logout-dialog',
				self.right_session_pane,
			],
			[
				_('Shut Down...'),
				_('Shut down the system'),
				'system-shutdown',
				'gnome-session-save --shutdown-dialog',
				self.right_session_pane,
			],
		]

		for item in items:

			button = self.add_launcher_entry(item[0], item[2], self.session_section_contents, 'raw', item[3], tooltip = item[1], app_list = self.app_list)
			button = self.add_button(item[0], item[2], item[4], tooltip = item[1], is_launcher_button = True)


	def build_system_list(self):

		self.add_tree_to_app_list(self.sys_tree.root, self.system_section_contents)


	def build_applications_list(self):

		for node in self.app_tree.root.contents:

			if isinstance(node, gmenu.Directory):

				# add to main pane
				self.add_slab(node.name, node.icon, node.get_comment(), node = node, hide = False)


	def add_slab(self, title_str, icon_name = None, tooltip = '', hide = False, node = None, append = True):

		# add category to category pane
		sidebar_button = self.add_sidebar_button(title_str, icon_name, self.category_pane, tooltip = tooltip, append = append)

		# add category to application pane
		section_slab, section_contents, dummy = self.add_application_section(title_str, append = append)

		if node is not None:
			# add all apps in this category to application pane
			self.add_tree_to_app_list(node, section_contents)

		sidebar_button.connect('clicked', self.on_sidebar_button_clicked, section_slab)

		if hide:
			sidebar_button.hide()
			section_slab.hide()
			self.section_list[section_slab] = {
					'has entries': False, 
					'category': sidebar_button, 
					'contents': section_contents, 
					'name': title_str,
					}

		else:
			self.section_list[section_slab] = {
					'has entries': True, 
					'category': sidebar_button, 
					'contents': section_contents, 
					'name': title_str,
					}

		return section_slab, section_contents


	def add_help_slab(self):

		section_slab, section_contents = self.add_slab(_('Help'), 'system-help', hide = True)
		self.help_section_slab = section_slab
		self.help_section_contents = section_contents


	def add_places_slab(self):

		section_slab, section_contents = self.add_slab(_('Places'), 'folder', tooltip = _('Access documents and folders'), hide = False)
		self.places_section_contents = section_contents


	def add_favorites_slab(self):

		section_slab, section_contents = self.add_slab(_('Pinned items'), 'emblem-favorite', tooltip = _('Your favorite applications'), hide = False, append = False)
		self.favorites_section_slab = section_slab
		self.favorites_section_contents = section_contents


	def add_session_slab(self):

		section_slab, section_contents = self.add_slab(_('Session'), 'session-properties', hide = True)
		self.session_section_slab = section_slab
		self.session_section_contents = section_contents


	def add_system_slab(self):

		section_slab, section_contents = self.add_slab(_('System'), 'applications-system', hide = True)
		self.system_section_slab = section_slab
		self.system_section_contents = section_contents


	def add_plugin_slab(self, plugin):

		append = (plugin.category_position == 'end')
		section_slab, section_contents = self.add_slab(plugin.category_name, plugin.category_icon, hide = plugin.hide_from_sidebar, append = append)
		return section_slab, section_contents


	def clear_pane(self, container):

		for	child in container.get_children():
			container.remove(child)


	def clear_search_entry(self):

		self.search_entry.set_text('')


	def add_sidebar_button(self, button_str, icon_name, parent_widget, tooltip = '', use_toggle_button = True, append = True):

		return self.add_button(button_str, icon_name, parent_widget, tooltip, use_toggle_button = use_toggle_button, is_launcher_button = False, append = append)


	def add_launcher_entry(self, button_str, icon_name, parent_widget, command_type, command, tooltip = '', app_list = None):

		button = self.add_button(button_str, icon_name, parent_widget, tooltip, is_launcher_button = True)

		if app_list is not None:
			app_list.append({'name': button_str.lower(), 'button': button, 'section': parent_widget.parent.parent})
			# save the app name, its button, and the section slab it came from
			# NOTE: IF THERE ARE CHANGES IN THE UI FILE, THIS MAY PRODUCE
			# HARD-TO-FIND BUGS!!

		button.connect('button-press-event', self.on_appbutton_button_pressed)

		if command_type == 'app':
			button.connect('clicked', self.on_appbutton_clicked, command)

		elif command_type == 'raw':
			button.connect('clicked', self.on_raw_button_clicked, command)

		elif command_type == 'xdg':
			button.connect('clicked', self.on_xdg_button_clicked, command)

		# save some metadata for easy access
		button.launcher_info = {}
		button.launcher_info['name']      = self.unescape(button_str)
		button.launcher_info['tooltip']   = tooltip
		button.launcher_info['icon_name'] = icon_name
		button.launcher_info['command']   = command
		button.launcher_info['type']      = command_type

		return button


	def add_button(self, button_str, icon_name, parent_widget, tooltip = '', use_toggle_button = None, is_launcher_button = True, append = True):

		if is_launcher_button or use_toggle_button == False:
			button = gtk.Button()
		else:
			button = gtk.ToggleButton()

		button_str = self.unescape(button_str)
		tooltip = self.unescape(tooltip)

		label = gtk.Label(button_str)

		if is_launcher_button:
			icon_size = self.icon_size_app
			label.modify_fg(gtk.STATE_NORMAL, self.style_appbutton_fg)
			# TODO: figure out how to set max width so that it is the best for
			# the window and font sizes
			#label.set_ellipsize(pango.ELLIPSIZE_END)
			#label.set_max_width_chars(20)
		else:
			icon_size = self.icon_size_category

		icon_size_pixels = gtk.icon_size_lookup(icon_size)[0]
		icon = self.get_icon(icon_name, icon_size_pixels)

		hbox = gtk.HBox()
		hbox.add(icon)
		hbox.add(label)
		hbox.set_spacing(5)
		hbox.set_homogeneous(False)

		align = gtk.Alignment(0, 0.5)
		align.add(hbox)

		if tooltip: button.set_tooltip_text(tooltip)

		button.add(align)
		button.set_relief(gtk.RELIEF_NONE)
		button.set_use_underline(False)

		button.show_all()
		#if append:
		#	parent_widget.pack_end(button, expand = False, fill = False)
		#else:
		parent_widget.pack_start(button, expand = False, fill = False)

		return button


	def add_application_section(self, section_title = None, append = True):

		section_slab, section_contents = self.add_section()

		if section_title is not None:
			label = section_slab.get_label_widget()
			label.set_text(section_title)
			label.modify_fg(gtk.STATE_NORMAL, self.style_appbutton_fg)

		s = str(len(section_slab));
		c = str(len(section_contents));

		section_slab.set_name('SectionSlab' + s)
		section_contents.set_name('SectionContents' + s + c)

		#if append:
		#	self.application_pane.pack_end(section_slab, expand = False, fill = False)
		#else:
		self.application_pane.pack_start(section_slab, expand = False, fill = False)

		return section_slab, section_contents, label


	def add_section(self):

		builder = gtk.Builder()
		builder.add_from_file(self.uifile)
		section_slab = builder.get_object('SectionSlab')
		section_contents = builder.get_object('SectionContents')

		if section_slab.parent is not None:
			section_slab.parent.remove(section_slab)

		del builder
		return section_slab, section_contents



	def get_icon(self, icon_value, icon_size, fallback_icon = 'application-x-executable'):

		if not icon_value: 
			icon_value = fallback_icon

		icon_pixbuf = None
		icon_name = icon_value

		if os.path.isabs(icon_value):
			if os.path.isfile(icon_value):
				icon_pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(icon_value, icon_size, icon_size)
			icon_name = os.path.basename(icon_value)

		if re.match('.*\.(png|xpm|svg)$', icon_name) is not None:
			icon_name = icon_name[:-4]

		if icon_pixbuf is None:
			if self.icon_theme.has_icon(icon_name):
				icon_pixbuf = self.icon_theme.load_icon(icon_name, icon_size, gtk.ICON_LOOKUP_FORCE_SIZE)

			else:
				for dir_ in BaseDirectory.xdg_data_dirs:
					for subdir in ('pixmaps', 'icons'):
						path = os.path.join(dir_, subdir, icon_value)
						if os.path.isfile(path):
							icon_pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(path, icon_size, icon_size)

		if icon_pixbuf is None:
			icon_pixbuf = self.icon_theme.load_icon(fallback_icon, icon_size, gtk.ICON_LOOKUP_FORCE_SIZE)

		return gtk.image_new_from_pixbuf(icon_pixbuf)


	def add_tree_to_app_list(self, tree, parent_widget, recursive = True):

		has_no_leaves = True

		for node in tree.contents:

			if isinstance(node, gmenu.Entry):

				button = self.add_launcher_entry(node.name, node.icon, parent_widget, 'app', node.desktop_file_path, tooltip = node.get_comment(), app_list = self.app_list)
				has_no_leaves = False

			elif isinstance(node, gmenu.Directory) and recursive:

				self.add_tree_to_app_list(node, parent_widget)

		return has_no_leaves


	def prepare_colors(self):

		dummy_window = gtk.Window()
		dummy_window.realize()
		app_style = dummy_window.get_style()
		self.style_appbutton_bg = app_style.base[gtk.STATE_NORMAL]
		self.style_appbutton_fg = app_style.text[gtk.STATE_NORMAL]
		self.get_object('ScrolledViewport').modify_bg(gtk.STATE_NORMAL, self.style_appbutton_bg)


	def launch_edit_app(self, *dummy):

		self.launch_raw('alacarte')


	def on_pin_this_app_clicked(self, widget):

		self.settings['pinned items'].append(self.app_clicked)
		self.clear_pane(self.favorites_section_contents)
		self.build_favorites_list()


	def on_unpin_this_app_clicked(self, widget):

		self.settings['pinned items'].remove(self.app_clicked)
		self.clear_pane(self.favorites_section_contents)
		self.build_favorites_list()


	def on_appbutton_button_pressed(self, widget, event):

		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:

			already_pinned = False

			for command in [app['command'] for app in self.settings['pinned items']]:
				if command == widget.launcher_info['command']: 
					already_pinned = True
					break

			if already_pinned:
				self.pin_menuitem.hide()
				self.unpin_menuitem.show()
			else:
				self.pin_menuitem.show()
				self.unpin_menuitem.hide()

			self.app_clicked = widget.launcher_info

			self.block_focus_out_event()
			self.app_context_menu.popup(None, None, None, event.button, event.time)


	def on_appbutton_clicked(self, widget, desktop_path):

		if os.path.exists(desktop_path):

			path = DesktopEntry.DesktopEntry(desktop_path).getExec()

			# Strip last part of path if it contains %<a-Z>
			match = self.exec_pattern.match(path)

			if match is not None:
				path = match.group(1)

			return self.launch_raw(path)

		else:
			logging.warn('Warning: Tried launching an app that does not exist: %s' % desktop_path)


	def on_xdg_button_clicked(self, widget, path):

		self.launch_xdg(path)


	def launch_xdg(self, path):

		path = self.escape_quotes(self.unescape(path))
		return self.launch_raw("xdg-open '%s'" % path)


	def on_raw_button_clicked(self, widget, path):

		self.launch_raw(path)


	def launch_raw(self, path):

		try:
			subprocess.Popen(path, shell = True, cwd = self.user_home_folder)
		except OSError:
			return False

		self.hide()
		return True


	def show_all_nonempty_sections(self):

		self.no_results_to_show = True

		for sec in self.section_list:
			if self.section_list[sec]['has entries']:
				sec.show()
				self.no_results_to_show = False
			else:
				sec.hide()

		if self.no_results_to_show:
			self.show_no_results_text()
		else:
			self.hide_no_results_text()

		if self.selected_section is not None:
			widget = self.section_list[self.selected_section]['category']
			self.set_sidebar_button_active(widget, False)

		self.selected_section = None

		widget = self.all_sections_sidebar_button
		self.set_sidebar_button_active(widget, True) 

		if self.is_searchfield_empty():
			widget.set_sensitive(False)


	def show_lone_section(self, section_slab):

		for sec in self.section_list:
			sec.hide()

		if self.selected_section is not None:
			widget = self.section_list[self.selected_section]['category']
			self.set_sidebar_button_active(widget, False)

		elif self.all_sections_sidebar_button.get_active():
			widget = self.all_sections_sidebar_button
			self.set_sidebar_button_active(widget, False)

		self.all_sections_sidebar_button.set_sensitive(True)
		self.selected_section = section_slab

		self.consider_showing_no_results_text()
 		self.scroll_to_top()


	def show_no_results_text(self, text = None):

		if text is None: text = _('No results to show')

		self.no_results_label.set_text(text)
		self.no_results_slab.show()


	def hide_no_results_text(self):

		self.no_results_slab.hide()


	def consider_showing_no_results_text(self):

		if self.selected_section is None:

			if self.no_results_to_show:
				self.show_no_results_text()

			return 
			
		if self.section_list[self.selected_section]['has entries']:
			self.selected_section.show()
			self.hide_no_results_text()

		else:
			self.selected_section.hide()
			self.show_no_results_text(_('No results to show in "%(category_name)s"') % {'category name': self.section_list[self.selected_section]['name']})


	def hide_all_transitory_sections(self, fully_hide = False):

		self.hide_section(self.help_section_slab   , fully_hide)
		self.hide_section(self.session_section_slab, fully_hide)
		self.hide_section(self.system_section_slab , fully_hide)
		
		self.hide_plugin_sections(fully_hide)


	def hide_section(self, section_slab, fully_hide = False):

		if fully_hide:
			self.set_section_is_empty(section_slab)

		section_slab.hide()


	def hide_plugin_sections(self, fully_hide = False):

		for plugin in self.active_plugin_instances:
			if plugin.hide_from_sidebar:
				self.hide_section(plugin.section_slab, fully_hide)


	def show_section(self, section_slab, fully_show = False):

		if fully_show:
			self.set_section_has_entries(section_slab)

		section_slab.show()


	def set_section_is_empty(self, section_slab):

		self.section_list[section_slab]['has entries'] = False
		self.section_list[section_slab]['category'].hide()


	def set_section_has_entries(self, section_slab):

		self.section_list[section_slab]['has entries'] = True
		self.section_list[section_slab]['category'].show()


	def set_sidebar_button_active(self, button, state):

		if button.get_active() != state:
			self.auto_toggled_sidebar_button = True
			button.set_active(state)


	def scroll_to_section(self, widget, session_slab):

		self.scroll_to_widget(session_slab)


	def scroll_to_widget(self, widget):

		alloc = widget.get_allocation()
		self.scroll_adjustment.set_value(min(alloc.y, self.scroll_adjustment.upper - self.scroll_adjustment.page_size))


	def scroll_to_top(self):

		self.scroll_adjustment.set_value(0)


	def unescape(self, mystr):

		return urllib2.unquote(str(mystr)) # NOTE: it is possible that with python3 we will have to change this line


	def escape_quotes(self, mystr):

		mystr = re.sub("'", "\\'", mystr)
		mystr = re.sub('"', '\\"', mystr)
		return mystr


class CardapioPluginInterface:

	author             = ''
	name               = '' # use gettext for name
	description        = '' # use gettext for description

	# not yet used:
	url                = ''
	help_text          = ''
	version            = ''

	plugin_api_version = 1.1

	# one of: None, 'local search update delay', 'remote search update delay'
	search_delay_type  = 'local search update delay'

	category_name      = '' # use gettext for category
	category_icon      = '' # TODO: implement this
	category_position  = 'end' # one of: 'start' or 'end'
	hide_from_sidebar  = True

	# TODO: add to the plugin API (post version 1.0):
	# keyword  - plugin will only be executed if the keyword is the first word in the query
	# shortcut - a letter or number so that Alt+letter selects this plugin's category
	# what else?

	is_running = False

	def __init__(self, settings, write_to_log, handle_search_result, handle_search_error):
		"""
		This constructor gets called whenever a plugin is activated.
		(Typically once per session, unless the user is turning plugins on/off)

		The constructor *must* set the instance variable self.loaded to True of False.
		For example, the Tracker plugin sets self.loaded to False if Tracker is not
		installed in the system.
		
		Note: DO NOT WRITE ANYTHING IN THE settings DICT!!
		"""
		self.loaded = False


	def __del__(self):
		"""
		This destructor gets called whenever a plugin is deactivated
		(Typically once per session, unless the user is turning plugins on/off)
		"""
		pass
		

	def search(self, text):
		"""
		REQUIRED 

		This method gets called when a new text string is entered in the search
		field. It must output a list where each item is a dict following format
		below:

		item = {}

		# required:
		item['name'] = 'Music'
		item['tooltip'] = 'Show your Music folder'
		item['icon name'] = 'text-x-generic'
		item['xdg uri'] = '~/Music' 

		Where 'xdg uri' is a URI that works with the terminal command xdg-open
		(in the future, 'xdg uri' will probably be optional, and you'll be able
		to provide your own methods for handling the onclick even of the search
		results)
		"""
		pass


	def cancel(self):
		"""
		Cancels the current search operation.
		"""
		pass



# make a few of useful modules and functions available to plugins
import __builtin__
__builtin__._ = _
__builtin__.dbus = dbus
__builtin__.CardapioPluginInterface = CardapioPluginInterface
__builtin__.logging = logging


def return_true(*dummy):
	return True


def applet_factory(applet, iid):

	button = gtk.ImageMenuItem()

	cardapio = Cardapio(hidden = True, panel_button = button, panel_applet = applet)

	button.set_tooltip_text(_('Access applications, folders, system settings, etc.'))
	button.set_always_show_image(True)

	menu = gtk.MenuBar()
	menu.set_name('CardapioAppletMenu')
	menu.add(button)

	button.connect('button-press-event', cardapio.on_panel_button_toggled)
	menu.connect('button-press-event', cardapio.on_panel_button_pressed)

	# make sure menuitem doesn't change focus on mouseout/mousein
	button.connect('enter-notify-event', return_true)
	button.connect('leave-notify-event', return_true)

	gtk.rc_parse_string('''
		style "cardapio-applet-menu-style"
		{
			xthickness = 0
			ythickness = 0
			GtkMenuBar::shadow-type = none
			GtkMenuBar::internal-padding = 0
			GtkWidget::focus-padding = 0
			GtkMenuBar::focus-padding = 0
			#bg[NORMAL] = "#ff0000"
		}

		style "cardapio-applet-style"
		{
			xthickness = 0
			ythickness = 0
			GtkWidget::focus-line-width = 0
			GtkWidget::focus-padding = 0
		}

		widget "*CardapioAppletMenu" style:highest "cardapio-applet-menu-style"
		widget "*PanelApplet" style:highest "cardapio-applet-style"
		#widget "*Cardapio.*" style:highest "cardapio-applet-style"
		''')

	applet.add(menu)

	applet.connect('size-allocate', cardapio.on_panel_size_changed)
	applet.connect('change-orient', cardapio.panel_change_orientation)
	applet.connect('change-background', cardapio.on_panel_change_background)

	applet.set_applet_flags(gnomeapplet.EXPAND_MINOR)
	applet.show_all()

	cardapio.panel_change_orientation()

	return True


