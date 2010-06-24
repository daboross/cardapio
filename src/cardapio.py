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


# Set up translations

cardapio_path = os.path.dirname(os.path.realpath(__file__))
prefix_path = cardapio_path.split(os.path.sep)[:-2]
prefix_path = [os.path.sep] + prefix_path + ['share', 'locale']

DIR = os.path.join(*prefix_path)
APP = 'cardapio'

locale.setlocale(locale.LC_ALL, '')
gettext.bindtextdomain(APP, DIR)

if hasattr(gettext, 'bind_textdomain_codeset'):
    gettext.bind_textdomain_codeset(APP, 'UTF-8')

gettext.textdomain(APP)
_ = gettext.gettext


# Hack for making translations work with ui files

import gtk.glade
gtk.glade.bindtextdomain(APP, DIR)
gtk.glade.textdomain(APP)


# Main Cardapio class

class Cardapio(dbus.service.Object):

	distro_name = commands.getoutput('lsb_release -is')

	min_visibility_toggle_interval = 0.010 # seconds (this is a bit of a hack to fix some focus problems)

	bus_name_str = 'org.varal.Cardapio'
	bus_obj_str  = '/org/varal/Cardapio'

	version = '0.9.112'

	def __init__(self, hidden = False, panel_applet = None, panel_button = None):

		self.create_config_folder()
		log_file_path = os.path.join(self.config_folder_path, 'cardapio.log')

		logging.basicConfig(filename = log_file_path, level = logging.DEBUG)
		logging.info('----------------- Cardapio launched -----------------')

		self.home_folder_path = os.path.abspath(os.path.expanduser('~'))

		self.read_config_file()

		self.panel_applet = panel_applet
		self.panel_button = panel_button
		self.auto_toggled_sidebar_button = False
		self.last_visibility_toggle = 0

		self.visible                       = False
		self.app_list                      = []    # used for searching the menu
		self.section_list                  = {}
		self.selected_section              = None
		self.no_results_to_show            = False
		self.previously_focused_widget     = None
		self.opened_last_app_in_background = False
		self.focus_out_blocked             = False
		self.clicked_app                   = None
		self.keybinding                    = None
		self.search_timer_local            = None
		self.search_timer_remote           = None
		self.plugin_database               = {}
		self.active_plugin_instances       = []

		self.app_tree = gmenu.lookup_tree('applications.menu')
		self.sys_tree = gmenu.lookup_tree('settings.menu')
		self.app_tree.add_monitor(self.on_menu_data_changed)
		self.sys_tree.add_monitor(self.on_menu_data_changed)

		self.exec_pattern = re.compile("^(.*?)\s+\%[a-zA-Z]$")

		self.package_root = ''
		if __package__ is not None:
			self.package_root = __package__ + '.'

		self.setup_dbus()
		self.setup_base_ui() # must be the first ui-related method to be called
		self.build_plugin_database() 
		self.activate_plugins_from_settings()
		self.build_ui() 
		self.setup_ui_from_all_settings() 

		self.schedule_search_with_plugins('')

		if not hidden: self.show()

		# this is useful so that the user can edit the config file on first-run 
		# without need to quit cardapio first:
		self.save_config_file()


	def on_mainwindow_destroy(self, widget):
		"""
		Handler for when the Cardapio window is destroyed
		"""

		self.quit()


	def quit(self, *dummy):
		"""
		Saves the current state and quits
		"""

		self.save_config_file()
		gtk.main_quit()


	def setup_dbus(self):
		"""
		Sets up the session bus
		"""

		DBusGMainLoop(set_as_default=True)
		self.bus = dbus.SessionBus()
		dbus.service.Object.__init__(self, self.bus, Cardapio.bus_obj_str)

	
	def get_plugin_class(self, basename):
		""" 
		Returns the CardapioPlugin class from the plugin at plugins/basename.py.
		If it fails, it returns a string decribing the error.
		"""

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
		"""
		Searches the plugins/ folder for .py files not starting with underscore.
		Creates the dict self.plugin_database indexed by the plugin filename's base name.
		"""

		self.plugin_database = {}
		plugin_dirs = [
			os.path.join(cardapio_path, 'plugins'), 
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
		"""
		Initializes plugins in the database if the user's settings say so.
		"""

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

			plugin.basename         = basename
			plugin.is_running       = False

			self.active_plugin_instances.append(plugin)


	def write_to_plugin_log(self, plugin, text, is_error = False, is_warning = False):
		"""
		Writes 'text' to the log file, prefixing it with [plugin name].
		"""

		if is_error: 
			write = logging.error

		elif is_warning: 
			write = logging.warning

		else:
			write = logging.debug

		write('[%s] %s'  % (plugin.name, text))


	def on_all_sections_sidebar_button_clicked(self, widget):
		"""
		Handler for when the user clicks "All" in the sidebar
		"""

		if self.auto_toggled_sidebar_button:
			self.auto_toggled_sidebar_button = False
			return True

		if self.selected_section is None:
			self.clear_search_entry()
			widget.set_sensitive(False)

		else:
			self.show_all_nonempty_sections()


	def on_sidebar_button_clicked(self, widget, section_slab):
		"""
		Handler for when the user chooses a category in the sidebar
		"""

		if self.auto_toggled_sidebar_button:
			self.auto_toggled_sidebar_button = False
			return True

		if self.selected_section == section_slab:
			self.selected_section = None # necessary!
			self.show_all_nonempty_sections()
			return True

		self.show_lone_section(section_slab)


	def create_config_folder(self):
		"""
		Creates Cardapio's config folder (usually at ~/.config/Cardapio)
		"""

		self.config_folder_path = os.path.join(DesktopEntry.xdg_config_home, 'Cardapio')

		if not os.path.exists(self.config_folder_path): 
			os.mkdir(self.config_folder_path)

		elif not os.path.isdir(self.config_folder_path):
			logging.error('Error! Cannot create folder "%s" because a file with that name already exists!' % self.config_folder_path)
			sys.exit(1)


	def get_config_file(self, mode):
		"""
		Returns a file handler to Cardapio's config file.
		"""

		config_file_path = os.path.join(self.config_folder_path, 'config.ini')

		if not os.path.exists(config_file_path):
			open(config_file_path, 'w+')

		elif not os.path.isfile(config_file_path):
			logging.error('Error! Cannot create file "%s" because a folder with that name already exists!' % config_file_path)
			sys.exit(1)

		return open(config_file_path, mode)


	def read_config_file(self):
		"""
		Reads Cardapio's config file and builds the self.settings dict
		"""

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

		default_side_pane_items = []
		default_side_pane_items.append(
			{
				'name'      : _('Control Center'),
				'icon name' : 'gnome-control-center',
				'tooltip'   : _('The Gnome configuration tool'),
				'type'      : 'raw',
				'command'   : 'gnome-control-center',
			})

		path = commands.getoutput('which software-center')
		if os.path.exists(path):
			default_side_pane_items.append(
				{
					'name'      : _('Ubuntu Software Center'), 
					'icon name' : 'softwarecenter',
					'tooltip'   : _('Lets you choose from thousands of free applications available for Ubuntu'), 
					'type'      : 'raw',
					'command'   : 'software-center', 
				})

		default_side_pane_items.append(
			{
				'name'      : _('Help and Support'), 
				'icon name' : 'help-contents',
				'tooltip'   : _('Get help with %(distro_name)s') % {'distro_name':Cardapio.distro_name}, 
				'type'      : 'raw',
				'command'   : 'gnome-help', 
			})

		self.read_config_option(s, 'window size'                , None                     ) # format: [px, px]
		self.read_config_option(s, 'splitter position'          , 0                        ) # int in pixels
		self.read_config_option(s, 'show session buttons'       , False                    ) # bool
		self.read_config_option(s, 'open on hover'              , False                    ) # bool
		self.read_config_option(s, 'min search string length'   , 3                        ) # characters
		self.read_config_option(s, 'menu rebuild delay'         , 10                       , force_update_from_version = [0,9,96]) # seconds
		self.read_config_option(s, 'search results limit'       , 5                        ) # results
		self.read_config_option(s, 'local search update delay'  , 100                      , force_update_from_version = [0,9,96]) # msec
		self.read_config_option(s, 'remote search update delay' , 250                      , force_update_from_version = [0,9,96]) # msec
		self.read_config_option(s, 'keybinding'                 , '<Super>space'           ) # the user should use gtk.accelerator_parse('<Super>space') to see if the string is correct!
		self.read_config_option(s, 'applet label'               , Cardapio.distro_name     ) # string
		self.read_config_option(s, 'applet icon'                , 'start-here'             , override_empty_str = True) # string (either a path to the icon, or an icon name)
		self.read_config_option(s, 'pinned items'               , []                       ) 
		self.read_config_option(s, 'side pane items'            , default_side_pane_items  )
		self.read_config_option(s, 'active plugins'             , ['tracker', 'google']    ) # filenames

		self.settings['cardapio version'] = self.version

		# clean up the config file whenever options are renamed between versions

		if 'system pane' in self.settings:
			self.settings['side pane'] = self.settings['system pane']
			self.settings.pop('system pane')


	def read_config_option(self, user_settings, key, val, override_empty_str = False, force_update_from_version = None):
		"""
		Reads the config option 'key' from a the 'user_settings' dict, using
		'val' as a fallback.
		"""

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
		"""
		Saves the self.settings dict into the config file
		"""

		self.settings['splitter position'] = self.get_object('MainSplitter').get_position()

		config_file = self.get_config_file('w')
		json.dump(self.settings, config_file, sort_keys = True, indent = 4)


	def setup_base_ui(self):
		"""
		Reads the GTK Builder interface file and sets up some UI details
		"""

		self.rebuild_timer = None

		self.uifile = os.path.join(cardapio_path, 'cardapio.ui')

		self.builder = gtk.Builder()
		self.builder.set_translation_domain(APP)
		self.builder.add_from_file(self.uifile)
		self.builder.connect_signals(self)

		# HACK: fix names of widgets to allow theming 
		# (glade doesn't seem to properly add names to widgets anymore...)
		for widget in self.builder.get_objects():
			if 'set_name' in dir(widget):
				widget.set_name(gtk.Buildable.get_name(widget))

		self.get_object = self.builder.get_object
		self.window                    = self.get_object('MainWindow')
		self.message_window            = self.get_object('MessageWindow')
		self.about_dialog              = self.get_object('AboutDialog')
		self.options_dialog            = self.get_object('OptionsDialog')
		self.application_pane          = self.get_object('ApplicationPane')
		self.category_pane             = self.get_object('CategoryPane')
		self.sidepane                  = self.get_object('SideappPane')
		self.search_entry              = self.get_object('SearchEntry')
		self.scrolled_window           = self.get_object('ScrolledWindow')
		self.scroll_adjustment         = self.scrolled_window.get_vadjustment()
		self.session_pane              = self.get_object('SessionPane')
		self.left_session_pane         = self.get_object('LeftSessionPane')
		self.right_session_pane        = self.get_object('RightSessionPane')
		self.context_menu              = self.get_object('CardapioContextMenu')
		self.app_context_menu          = self.get_object('AppContextMenu')
		self.pin_menuitem              = self.get_object('PinMenuItem')
		self.unpin_menuitem            = self.get_object('UnpinMenuItem')
		self.add_side_pane_menuitem    = self.get_object('AddSidePaneMenuItem')
		self.remove_side_pane_menuitem = self.get_object('RemoveSidePaneMenuItem')
		self.plugin_tree_model         = self.get_object('PluginListstore')

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
				<separator />
				<menuitem name="Item 3" verb="AboutCardapio" label="%s" pixtype="stock" pixname="gtk-about"/>
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
		"""
		Returns the best icon size for the current panel size
		"""

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
		"""
		Sets up the look and feel of the Cardapio applet button 
		"""

		self.panel_button.set_label(self.settings['applet label'])
		button_icon = self.get_icon(self.settings['applet icon'], self.get_best_icon_size(), 'distributor-logo')
		self.panel_button.set_image(button_icon)

		if self.panel_button.parent is None: return

		self.panel_button.parent.connect('button-press-event', self.on_panel_button_pressed)

		if 'applet_press_handler' in dir(self):
			self.panel_button.disconnect(self.applet_press_handler)
			self.panel_button.disconnect(self.applet_enter_handler)

		if self.settings['open on hover']:
			self.applet_press_handler = self.panel_button.connect('button-press-event', self.hide)
			self.applet_enter_handler = self.panel_button.connect('enter-notify-event', self.show)

		else:
			self.applet_press_handler = self.panel_button.connect('button-press-event', self.on_panel_button_toggled)
			self.applet_enter_handler = self.panel_button.connect('enter-notify-event', lambda x, y: True)


	def setup_ui_from_all_settings(self):
		"""
		Setup UI elements according to user preferences
		"""

		self.setup_ui_from_gui_settings()

		if self.settings['splitter position'] > 0:
			self.get_object('MainSplitter').set_position(self.settings['splitter position'])

		self.restore_dimensions()


	def setup_ui_from_gui_settings(self):
		"""
		Setup UI elements from the set of preferences that are accessible
		from the options dialog.
		"""

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
		"""
		Read the contents of all menus and plugins and build the UI
		elements that support them.
		"""

		self.prepare_colors()

		self.clear_pane(self.application_pane)
		self.clear_pane(self.category_pane)
		self.clear_pane(self.sidepane)
		self.clear_pane(self.left_session_pane)
		self.clear_pane(self.right_session_pane)

		self.app_list = []      # holds a list of all apps for searching purposes
		self.section_list = {}  # holds a list of all sections to allow us to reference them by their "slab" widgets

		button = self.add_sidebar_button(_('All'), None, self.category_pane, tooltip = _('Show all categories'))
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_sections_sidebar_button = button 
		self.set_sidebar_button_active(button, True)
		self.all_sections_sidebar_button.set_sensitive(False)

		self.no_results_slab, dummy, self.no_results_label = self.add_application_section('Dummy text')
		self.hide_no_results_text()

		if self.panel_applet is None:
			self.get_object('AppletOptionPane').hide()

		# slabs that should go *before* regular application slabs
		self.add_pinneditems_slab()
		self.add_sidepane_slab()
		self.add_places_slab()

		self.build_applications_list()

		# slabs that should go *after* regular application slabs
		self.add_session_slab()
		self.add_system_slab()
		self.add_uncategorized_slab()
		self.add_plugin_slabs()

		self.build_places_list()
		self.build_session_list()
		self.build_system_list()
		self.build_uncategorized_list()
		self.build_favorites_list(self.favorites_section_slab, 'pinned items')
		self.build_favorites_list(self.sidepane_section_slab, 'side pane items')

		self.set_message_window_visible(False)


	def rebuild_ui(self, show_message = False):
		"""
		Rebuild the UI after a timer (this is called when the menu data changes,
		for example)
		"""

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)
			self.rebuild_timer = None

		if show_message:
			self.set_message_window_visible(True)

		glib.idle_add(self.build_ui)


	def open_about_dialog(self, widget, verb = None):
		"""
		Opens either the "About Gnome" dialog, or the "About Ubuntu" dialog,
		or the "About Cardapio" dialog
		"""

		if verb == 'AboutGnome':
			self.launch_raw('gnome-about')

		elif verb == 'AboutDistro':
			self.launch_raw('yelp ghelp:about-%s' % Cardapio.distro_name.lower())
			# i'm assuming this is the pattern for all distros...

		else:
			self.about_dialog.show()


	def on_about_dialog_close(self, widget, response = None):
		"""
		Handler for hiding Cardapio's about dialog
		"""

		self.about_dialog.hide()


	def set_widget_from_option(self, widget_str, option_str):
		"""
		Set the value of the widget named 'widget_str' to 'option_str'
		"""

		widget = self.get_object(widget_str)
		widget.handler_block_by_func(self.on_options_changed)

		if type(widget) is gtk.Entry:
			widget.set_text(self.settings[option_str])

		elif type(widget) is gtk.CheckButton:
			widget.set_active(self.settings[option_str])

		else:
			logging.error('Widget %s (%s) was not written' % (widget_str, type(widget)))

		widget.handler_unblock_by_func(self.on_options_changed)


	def open_options_dialog(self, *dummy):
		"""
		Show the Options Dialog and populate its widgets with values from the
		user's settings (self.settings)
		"""

		self.set_widget_from_option('OptionKeybinding', 'keybinding')
		self.set_widget_from_option('OptionAppletLabel', 'applet label')
		self.set_widget_from_option('OptionAppletIcon', 'applet icon')
		self.set_widget_from_option('OptionSessionButtons', 'show session buttons')
		self.set_widget_from_option('OptionOpenOnHover', 'open on hover')

		self.plugin_tree_model.clear()

		# place active plugins at the top of the list, in order
		plugin_list = []
		plugin_list += [p.basename for p in self.active_plugin_instances]
		plugin_list += [basename for basename in self.plugin_database if basename not in plugin_list]

		for basename in plugin_list:

			active = (basename in self.settings['active plugins'])
			plugin_info = self.plugin_database[basename]

			title = _('<big><b>%(plugin_name)s</b></big>\n<i>by %(plugin_author)s</i>\n%(plugin_description)s') % {
					'plugin_name' : plugin_info['name'],
					'plugin_author': plugin_info['author'],
					'plugin_description': plugin_info['description'],
					}

			self.plugin_tree_model.append([basename, active, title])

		self.options_dialog.show()

	
	def close_options_dialog(self, *args):
		"""
		Hides the Options Dialog
		"""

		self.options_dialog.hide()
		self.save_config_file()
		return True


	def close_about_dialog(self, *args):
		"""
		Hides the About Dialog
		"""

		self.about_dialog.hide()
		return True


	def on_options_changed(self, *dummy):
		"""
		Updates Cardapio's options when the user alters them in the Options
		Dialog
		"""

		self.settings['keybinding'] = self.get_object('OptionKeybinding').get_text()
		self.settings['applet label'] = self.get_object('OptionAppletLabel').get_text()
		self.settings['applet icon'] = self.get_object('OptionAppletIcon').get_text()
		self.settings['show session buttons'] = self.get_object('OptionSessionButtons').get_active()
		self.settings['open on hover'] = self.get_object('OptionOpenOnHover').get_active()
		self.setup_ui_from_gui_settings()


	def on_plugin_apply_clicked(self, widget):
		"""
		Handler for when the user clicks on "Apply" in the plugin tab of the
		Options Dialog
		"""

		self.settings['active plugins'] = []
		iter_ = self.plugin_tree_model.get_iter_first()

		while iter_ is not None:

			if self.plugin_tree_model.get_value(iter_, 1):
				self.settings['active plugins'].append(self.plugin_tree_model.get_value(iter_, 0))

			iter_ = self.plugin_tree_model.iter_next(iter_)

		self.activate_plugins_from_settings()
		self.add_plugin_slabs()


	def on_plugin_state_toggled(self, cell, path):
		"""
		Believe it or not, GTK requires you to manually tell the checkbuttons
		that reside within a tree to toggle when the user clicks on them.
		This function does that.
		"""

		iter_ = self.plugin_tree_model.get_iter(path)
		self.plugin_tree_model.set_value(iter_, 1, not cell.get_active())	


	def on_mainwindow_button_pressed(self, widget, event):
		"""
		Show context menu when the right mouse button is clicked on the main
		window
		"""

		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
			self.block_focus_out_event()
			self.context_menu.popup(None, None, None, event.button, event.time)


	def start_resize(self, widget, event):
		"""
		This function is used to emulate the window manager's resize function
		from Cardapio's borderless window.
		"""

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
		"""
		Blocks the focus-out event
		"""

		if not self.focus_out_blocked:
			self.window.handler_block_by_func(self.on_mainwindow_focus_out)
			self.focus_out_blocked = True


	def unblock_focus_out_event(self, *dummy):
		"""
		If the focus-out event was previously blocked, this unblocks it
		"""

		if self.focus_out_blocked:
			self.window.handler_unblock_by_func(self.on_mainwindow_focus_out)
			self.focus_out_blocked = False


	def on_mainwindow_after_key_pressed(self, widget, event):
		"""
		Send all keypresses to the search entry, so the user can search
		from anywhere without the need to focus the search entry first
		"""

		w = self.window.get_focus()

		if w != self.search_entry and w == self.previously_focused_widget:

			if event.is_modifier: return

			self.previously_focused_widget = None
			self.window.set_focus(self.search_entry)
			self.search_entry.emit('key-press-event', event)


	def on_mainwindow_key_pressed(self, widget, event):
		"""
		This is a trick to make sure the user isn't already typing at the
		search entry when we redirect all keypresses to the search entry.
		Because that would enter two of each key.
		"""

		if self.window.get_focus() != self.search_entry:
			self.previously_focused_widget = self.window.get_focus()


	def on_mainwindow_focus_out(self, widget, event):
		"""
		Make Cardapio disappear when it loses focus
		"""

		applet_x, applet_y, dummy = self.panel_applet.window.get_pointer()
		dummy, dummy, applet_w, applet_h = self.panel_applet.get_allocation()

		# Make sure clicking the applet button doesn't cause a focus-out event.
		# Otherwise, the click signal actually happens *after* the focus-out,
		# which causes the applet to be re-shown rather than disappearing.
		# So by ignoring this focus-out we actually make sure that Cardapio
		# will be hidden after all. Silly.

		if self.panel_applet is not None and (0 <= applet_x <= applet_w and 0 <= applet_y <= applet_h): 
			return

		# If the last app was opened in the background, make sure Cardapio
		# doesn't hide when the app gets focused

		if self.opened_last_app_in_background:

			self.opened_last_app_in_background = False
			self.show_window_on_top(self.window)
			return

		self.hide()


	def on_mainwindow_delete_event(self, widget, event):
		"""
		What happens when the user presses Alt-F4? If in panel mode, 
		nothing. If in launcher mode, this terminates Cardapio.
		"""

		if self.panel_applet:
			# keep window alive if in panel mode
			return True


	def on_mainwindow_configure_event(self, widget, event):
		"""
		Save the window size whenever the user resizes Cardapio
		"""

		self.save_dimensions()


	def on_icon_theme_changed(self, icon_theme):
		"""
		Rebuild the Cardapio UI whenever the icon theme changes
		"""

		self.schedule_rebuild()


	def on_gtk_settings_changed(self, gobj, property_changed):
		"""
		Rebuild the Cardapio UI whenever the color scheme or gtk theme change
		"""

		if property_changed.name == 'gtk-color-scheme' or property_changed.name == 'gtk-theme-name':
			self.prepare_colors()
			self.schedule_rebuild()


	def on_menu_data_changed(self, tree):
		"""
		Rebuild the Cardapio UI whenever the menu data changes
		"""

		self.schedule_rebuild()


	def schedule_rebuild(self):
		"""
		Rebuilds the Cardapio UI after a timer
		"""

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)

		self.rebuild_timer = glib.timeout_add_seconds(self.settings['menu rebuild delay'], self.rebuild_ui)


	def on_searchentry_icon_pressed(self, widget, iconpos, event):
		"""
		Handler for when the "clear" icon of the search entry is pressed
		"""

		if self.is_searchentry_empty():
			self.show_all_nonempty_sections()

		else:
			self.clear_search_entry()


	def on_searchentry_changed(self, widget):
		"""
		Handler for when the user types something in the search entry
		"""

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
		"""
		Start a menu search
		"""

		text = text.lower()

		for sec in self.section_list:
			self.set_section_is_empty(sec)

		for app in self.app_list:

			if app['name'].find(text) == -1 and app['basename'].find(text) == -1:
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
		"""
		Start a plugin-based search, after some time-outs
		"""

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
		"""
		Start a plugin-based search
		"""

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
		"""
		Handler for when a plugin returns an error
		"""

		plugin.is_running = False
		self.write_to_plugin_log(plugin, text, is_error = True)
		self.handle_search_result(plugin, [])


	def handle_search_result(self, plugin, results):
		"""
		Handler for when a plugin returns some search results
		"""

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

			icon_name = result['icon name']
			fallback_icon = 'text-x-generic'

			if icon_name is not None:
				icon_name = self.get_icon_name_from_theme(icon_name)

			elif result['type'] == 'xdg':
				icon_name = self.get_icon_name_from_path(result['command'])

			if icon_name is None:
				icon_name = fallback_icon

			button = self.add_app_button(result['name'], icon_name, plugin.section_contents, result['type'], result['command'], tooltip = result['tooltip'])


		if results:

			self.no_results_to_show = False

			plugin.section_contents.show()
			self.set_section_has_entries(plugin.section_slab)

			if (self.selected_section is None) or (self.selected_section == plugin.section_slab):
				plugin.section_slab.show()
				self.hide_no_results_text()

			else:
				self.consider_showing_no_results_text()

		else:

			self.set_section_is_empty(plugin.section_slab)

			if (self.selected_section is None) or (self.selected_section == plugin.section_slab):
				plugin.section_slab.hide()

			self.consider_showing_no_results_text()

		gtk.gdk.threads_leave()


	def is_searchentry_empty(self):
		"""
		Returns True if the search entry is empty.
		"""

		return (len(self.search_entry.get_text().strip()) == 0)


	def on_searchentry_activate(self, widget):
		"""
		Handler for when the user presses Enter on the search entry
		"""

		for plugin in self.active_plugin_instances:
			if plugin.is_running: plugin.cancel()

		if self.is_searchentry_empty():
			self.hide_all_transitory_sections()
			return 

		first_app_widget = self.get_first_visible_app()
		if first_app_widget is not None:
			first_app_widget.emit('clicked')

		self.clear_search_entry()


	def on_searchentry_key_pressed(self, widget, event):
		"""
		Handler for when the user presses Tab or Escape on the search entry
		"""

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

			if not self.is_searchentry_empty():
				self.clear_search_entry()

			elif self.selected_section is not None:
				self.show_all_nonempty_sections()

			else:
				self.hide()

		else: return False
		return True


	def get_first_visible_app(self):
		"""
		Returns the first app in the right pane
		"""

		for slab in self.application_pane.get_children():
			if not slab.get_visible(): continue

			for app in slab.get_children()[0].get_children()[0].get_children():
				if not app.get_visible(): continue

				return app

		return None


	def reposition_window(self, is_message_window = False):
		"""
		Place the Cardapio window near the applet and make sure it's visible.
		If there is no applet, place it in the center of the screen.
		"""

		window_width, window_height = self.window.get_size()

		root_window = gtk.gdk.get_default_root_window()
		screen_property = gtk.gdk.atom_intern('_NET_WORKAREA')
		screen_dimensions = root_window.property_get(screen_property)[2]

		if screen_dimensions:
			screen_x      = screen_dimensions[0]
			screen_y      = screen_dimensions[1]
			screen_width  = screen_dimensions[2]
			screen_height = screen_dimensions[3]

		else:
			logging.warn('Could not get dimensions of usable screen area. Using max screen area instead.')
			screen_x, screen_y = 0, 0
			screen_width = gtk.gdk.screen_width()
			screen_height = gtk.gdk.screen_height()

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

		if window_x + window_width > screen_x + screen_width:
			window_x = screen_width - window_width

		if window_y + window_height > screen_y + screen_height:
			window_y = screen_height - window_height

		if window_x < screen_x:
			window_x = screen_x

		if window_y < screen_y:
			window_y = screen_y

		window.move(window_x + offset_x, window_y + offset_y)


	def restore_dimensions(self):
		"""
		Resize Cardapio according to the user preferences
		"""

		if self.settings['window size'] is not None: 
			self.window.resize(*self.settings['window size'])


	def save_dimensions(self):
		"""
		Save Cardapio's size into the user preferences
		"""

		self.settings['window size'] = self.window.get_size()


	def set_message_window_visible(self, state = True):
		"""
		Show/Hide the "Rebuilding" message window
		"""

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


	def show(self, *dummy):
		"""
		Show the Cardapio window
		"""

		self.auto_toggle_panel_button(True)

		self.restore_dimensions()
		self.reposition_window()
		self.show_window_on_top(self.window)

		self.window.set_focus(self.search_entry)
 		self.scroll_to_top()

		self.visible = True
		self.last_visibility_toggle = time.time()

		self.opened_last_app_in_background = False

		if self.rebuild_timer is not None:
			# build the UI *after* showing the window, so the user gets the
			# satisfaction of seeing the window pop up, even if it's incomplete...
			self.rebuild_ui(show_message = True)


	def hide(self, *dummy):
		"""
		Hide the Cardapio window
		"""

		self.auto_toggle_panel_button(False)

		self.visible = False
		self.last_visibility_toggle = time.time()

		self.save_dimensions()
		self.window.hide()

		self.clear_search_entry()
		self.show_all_nonempty_sections()


	@dbus.service.method(dbus_interface=bus_name_str, in_signature=None, out_signature=None)
	def show_hide(self):
		"""
		Toggle Show/Hide the Cardapio window. This function is dbus-accessible.
		"""

		if time.time() - self.last_visibility_toggle < Cardapio.min_visibility_toggle_interval:
			return

		if self.visible: self.hide()
		else: self.show()


	def show_window_on_top(self, window):
		"""
		Place the Cardapio window on top of all others
		"""

		window.show_now()

		# for compiz, this must take place twice!!
		window.present_with_time(int(time.time()))
		window.present_with_time(int(time.time()))

		# for metacity, this is required!!
		window.window.focus() 


	def on_panel_button_pressed(self, widget, event):
		"""
		Show the context menu when the user right-clicks the panel applet
		"""

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
		"""
		Show/Hide cardapio when the panel applet is clicked
		"""

		if event.type == gtk.gdk.BUTTON_PRESS:

			if event.button == 1:

				if self.visible: self.hide()
				else: self.show()

				return True # required! or we get strange focus problems


	def on_panel_size_changed(self, widget, allocation):
		"""
		Resize the panel applet when the panel size is changed
		"""

		self.panel_applet.handler_block_by_func(self.on_panel_size_changed)
		glib.timeout_add(100, self.setup_panel_button)
		glib.timeout_add(200, self.on_panel_size_change_done) # added this to avoid an infinite loop


	def on_panel_size_change_done(self):
		"""
		Restore a signal handler that we had deactivated
		"""

		self.panel_applet.handler_unblock_by_func(self.on_panel_size_changed)
		return False # must return false to cancel the timer


	def panel_change_orientation(self, *dummy):
		"""
		Resize the panel applet when the panel orientation is changed
		"""

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
		"""
		Update the Cardapio applet background when the user changes
		the panel background
		"""

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
		"""
		Toggle the panel applet when the user presses the keybinding
		"""

		if self.panel_applet is not None:

			if state: self.panel_button.select()
			else: self.panel_button.deselect()


	def remove_section_from_app_list(self, section_slab):
		"""
		Remove from the app list (used when searching) all apps that belong in a
		given section.
		"""

		i = 0
		while i < len(self.app_list):

			app = self.app_list[i]
			if section_slab == app['section']: self.app_list.pop(i)
			else: i += 1


	def build_system_list(self):
		"""
		Populate the System section
		"""

		self.add_tree_to_app_list(self.sys_tree.root, self.system_section_contents)


	def build_uncategorized_list(self):
		"""
		Populate the Uncategorized section
		"""

		self.add_tree_to_app_list(self.app_tree.root, self.uncategorized_section_contents, recursive = False)
		self.add_tree_to_app_list(self.sys_tree.root, self.uncategorized_section_contents, recursive = False)


	def build_places_list(self):
		"""
		Populate the places list
		"""

		button = self.add_app_button(_('Home'), 'user-home', self.places_section_contents, 'xdg', self.home_folder_path, tooltip = _('Open your personal folder'), app_list = self.app_list)
		button = self.add_app_button(_('Computer'), 'computer', self.places_section_contents, 'xdg', 'computer:///', tooltip = _('Browse all local and remote disks and folders accessible from this computer'), app_list = self.app_list)

		xdg_folders_file_path = os.path.join(DesktopEntry.xdg_config_home, 'user-dirs.dirs')
		xdg_folders_file = file(xdg_folders_file_path, 'r')

		# find desktop path and add desktop button
		for line in xdg_folders_file.readlines():

			res = re.match('\s*XDG_DESKTOP_DIR\s*=\s*"(.+)"', line)
			if res is not None:
				path = res.groups()[0]

				# check if the desktop path is the home folder, in which case we
				# do *not* need to add the desktop button.
				if os.path.abspath(path) == self.home_folder_path: break

				self.add_place(_('Desktop'), path, 'user-desktop')
				break

		xdg_folders_file.close()

		bookmark_file_path = os.path.join(self.home_folder_path, '.gtk-bookmarks')
		bookmark_file = file(bookmark_file_path, 'r')

		for line in bookmark_file.readlines():
			if line.strip(' \n\r\t'):
				name, path = self.get_place_name_and_path(line)
				# TODO: if path doesn't exist, add gio monitor (could be a removable disk)
				self.add_place(name, path, 'folder')

		bookmark_file.close()

		self.bookmark_monitor = gio.File(bookmark_file_path).monitor_file()  # keep a reference to avoid getting it garbage collected
		self.bookmark_monitor.connect('changed', self.on_bookmark_monitor_changed)

		button = self.add_app_button(_('Trash'), 'user-trash', self.places_section_contents, 'xdg', 'trash:///', tooltip = _('Open the trash'), app_list = self.app_list)


	def on_bookmark_monitor_changed(self, monitor, file, other_file, event):
		"""
		Handler for when the user adds/removes a bookmarked folder using
		Nautilus or some other program
		"""

		if event == gio.FILE_MONITOR_EVENT_CHANGES_DONE_HINT:

			# TODO: make sure this doesn't fire 5 times per change!

			for item in self.places_section_contents.get_children():
				self.places_section_contents.remove(item)

			self.build_places_list()


	def get_folder_name_and_path(self, folder_path):
		"""
		Returns a folder's name and path from its full filename
		"""

		path = folder_path.strip(' \n\r\t')

		res = folder_path.split(os.path.sep)
		if res: 
			name = res[-1].strip(' \n\r\t').replace('%20', ' ')
			if name: return name, path

		# TODO: handle remote folders like nautilus does (i.e. '/home on ftp.myserver.net')
		name = path.replace('%20', ' ')	
		return name, path


	def get_place_name_and_path(self, folder_path):
		"""
		Return the name and path of a bookmarked folder given a line from the
		gtk-bookmarks file
		"""

		res = folder_path.split(' ')
		if len(res) > 1: 
			name = ' '.join(res[1:]).strip(' \n\r\t')
			path = res[0]
			return name, path

		return self.get_folder_name_and_path(folder_path)


	def add_place(self, folder_name, folder_path, folder_icon):
		"""
		Add a folder to the Places list in Cardapio
		"""

		folder_path = os.path.expanduser(folder_path.replace('$HOME', '~')).strip(' \n\r\t')

		dummy, canonical_path = urllib2.splittype(folder_path)
		canonical_path = self.unescape(canonical_path)

		if not urllib2.posixpath.exists(canonical_path): return

		icon_name = self.get_icon_name_from_path(folder_path)
		if icon_name is None: icon_name = folder_icon
		button = self.add_app_button(folder_name, icon_name, self.places_section_contents, 'xdg', folder_path, tooltip = folder_path, app_list = self.app_list)


	def build_favorites_list(self, slab, list_name):
		"""
		Populate either the Pinned Items or Side Pane list
		"""

		text = self.search_entry.get_text().strip().lower()

		no_results = True 
		
		for app in self.settings[list_name]:

			# fixing a misspelling from the old config files...
			if 'icon_name' in app:
				app['icon name'] = app['icon_name']
				app.pop('icon_name')

			button = self.add_app_button(app['name'], app['icon name'], self.section_list[slab]['contents'], app['type'], app['command'], tooltip = app['tooltip'], app_list = self.app_list)

			if app['name'].lower().find(text) == -1:
				button.hide()

			else:
				button.show()
				self.set_section_has_entries(slab)
				self.no_results_to_show = False
				no_results = False

			if slab == self.sidepane_section_slab:

				app_info = button.app_info
				button = self.add_sidebar_button(app['name'], app['icon name'], self.sidepane, tooltip = app['tooltip'], use_toggle_button = False)
				button.app_info = app_info
				button.connect('clicked', self.on_app_button_clicked)
				button.connect('button-press-event', self.on_app_button_button_pressed)

		if no_results or (slab is self.sidepane_section_slab and not text):
			self.hide_section(slab, fully_hide = True)

		elif (self.selected_section is not None) and (self.selected_section != slab):
			self.hide_section(slab)

		else:
			self.show_section(slab, fully_show = True)


	def build_session_list(self):
		"""
		Populate the Session list
		"""

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

			button = self.add_app_button(item[0], item[2], self.session_section_contents, 'raw', item[3], tooltip = item[1], app_list = self.app_list)
			app_info = button.app_info
			button = self.add_button(item[0], item[2], item[4], tooltip = item[1], is_app_button = True)
			button.app_info = app_info
			button.connect('clicked', self.on_app_button_clicked)


	def build_applications_list(self):
		"""
		Populate the Applications list by reading the Gnome menus
		"""

		for node in self.app_tree.root.contents:

			if isinstance(node, gmenu.Directory):

				self.add_slab(node.name, node.icon, node.get_comment(), node = node, hide = False)


	def add_slab(self, title_str, icon_name = None, tooltip = '', hide = False, node = None):
		"""
		Add to the app pane a new section slab (i.e. a container holding a title
		label and a hbox to be filled with apps). This also adds the section
		name to the left pane, under the View label.
		"""

		# add category to category pane
		sidebar_button = self.add_sidebar_button(title_str, icon_name, self.category_pane, tooltip = tooltip)

		# add category to application pane
		section_slab, section_contents, dummy = self.add_application_section(title_str)

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


	def add_places_slab(self):
		"""
		Add the Places slab to the app pane
		"""

		section_slab, section_contents = self.add_slab(_('Places'), 'folder', tooltip = _('Access documents and folders'), hide = False)
		self.places_section_contents = section_contents


	def add_pinneditems_slab(self):
		"""
		Add the Pinned Items slab to the app pane
		"""

		section_slab, section_contents = self.add_slab(_('Pinned items'), 'emblem-favorite', tooltip = _('Your favorite applications'), hide = False)
		self.favorites_section_slab = section_slab
		self.favorites_section_contents = section_contents


	def add_sidepane_slab(self):
		"""
		Add the Side Pane slab to the app pane
		"""

		section_slab, section_contents = self.add_slab(_('Side Pane'), 'emblem-favorite', tooltip = _('Items pinned to the side pane'), hide = True)
		self.sidepane_section_slab = section_slab
		self.sidepane_section_contents = section_contents


	def add_uncategorized_slab(self):
		"""
		Add the Uncategorized slab to the app pane
		"""

		section_slab, section_contents = self.add_slab(_('Uncategorized'), 'applications-other', tooltip = _('Items that are not under any menu category'), hide = True)
		self.uncategorized_section_slab = section_slab
		self.uncategorized_section_contents = section_contents


	def add_session_slab(self):
		"""
		Add the Session slab to the app pane
		"""

		section_slab, section_contents = self.add_slab(_('Session'), 'session-properties', hide = True)
		self.session_section_slab = section_slab
		self.session_section_contents = section_contents


	def add_system_slab(self):
		"""
		Add the System slab to the app pane
		"""

		section_slab, section_contents = self.add_slab(_('System'), 'applications-system', hide = True)
		self.system_section_slab = section_slab
		self.system_section_contents = section_contents


	def add_plugin_slabs(self):

		for plugin in self.active_plugin_instances:

			section_slab, section_contents = self.add_slab(plugin.category_name, plugin.category_icon, hide = plugin.hide_from_sidebar)
			plugin.section_slab     = section_slab
			plugin.section_contents = plugin.section_slab.get_children()[0].get_children()[0]


	def clear_pane(self, container):
		"""
		Remove all children from a GTK container
		"""

		for	child in container.get_children():
			container.remove(child)


	def clear_search_entry(self):
		"""
		Clears the search entry
		"""

		self.search_entry.set_text('')


	def add_sidebar_button(self, button_str, icon_name, parent_widget, tooltip = '', use_toggle_button = True):
		"""
		Adds a button to the sidebar. This could be either a section button or
		one of the "left pane" buttons.
		"""

		return self.add_button(button_str, icon_name, parent_widget, tooltip, use_toggle_button = use_toggle_button, is_app_button = False)


	def add_app_button(self, button_str, icon_name, parent_widget, command_type, command, tooltip = '', app_list = None):
		"""
		Adds a new button to the app bar.
		"""

		button = self.add_button(button_str, icon_name, parent_widget, tooltip, is_app_button = True)

		if app_list is not None:

			path, basename = os.path.split(command)
			if basename : basename, dummy = os.path.splitext(basename)
			else        : basename = path

			app_list.append({'name': button_str.lower(), 'button': button, 'section': parent_widget.parent.parent, 'basename' : basename, 'command' : command})

			# NOTE: IF THERE ARE CHANGES IN THE UI FILE, THIS MAY PRODUCE
			# HARD-TO-FIND BUGS!!

		button.connect('clicked', self.on_app_button_clicked)
		button.connect('button-press-event', self.on_app_button_button_pressed)
		button.connect('focus-in-event', self.on_app_button_focused)

		# save some metadata for easy access
		button.app_info = {
			'name'       : self.unescape(button_str),
			'tooltip'    : tooltip,
			'icon name'  : icon_name,
			'command'    : command,
			'type'       : command_type,
		}

		return button


	def add_button(self, button_str, icon_name, parent_widget, tooltip = '', use_toggle_button = None, is_app_button = True):
		"""
		Adds a button to a parent container
		"""

		if is_app_button or use_toggle_button == False:
			button = gtk.Button()
		else:
			button = gtk.ToggleButton()

		button_str = self.unescape(button_str)
		tooltip = self.unescape(tooltip)

		label = gtk.Label(button_str)

		if is_app_button:
			icon_size = self.icon_size_app
			label.modify_fg(gtk.STATE_NORMAL, self.style_app_button_fg)
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
		parent_widget.pack_start(button, expand = False, fill = False)

		return button


	def add_application_section(self, section_title = None):
		"""
		Adds a new slab to the applications pane
		"""

		section_slab, section_contents = self.add_section()

		if section_title is not None:
			label = section_slab.get_label_widget()
			label.set_text(section_title)
			label.modify_fg(gtk.STATE_NORMAL, self.style_app_button_fg)

		s = str(len(section_slab));
		c = str(len(section_contents));

		section_slab.set_name('SectionSlab' + s)
		section_contents.set_name('SectionContents' + s + c)

		self.application_pane.pack_start(section_slab, expand = False, fill = False)

		return section_slab, section_contents, label


	def add_section(self):
		"""
		Reads the UI file to return the Slab structure (this makes it easier to
		design Cardapio, although it slows down the creation of new slabs in
		this code)
		"""

		builder = gtk.Builder()
		builder.add_from_file(self.uifile)
		section_slab = builder.get_object('SectionSlab')
		section_contents = builder.get_object('SectionContents')

		if section_slab.parent is not None:
			section_slab.parent.remove(section_slab)

		del builder
		return section_slab, section_contents


	def get_icon(self, icon_value, icon_size, fallback_icon = 'application-x-executable'):
		"""
		Returns a GTK Image from a given icon name and size. The icon name can be
		either a path or a named icon from the GTK theme.
		"""

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
			icon_name_ = self.get_icon_name_from_theme(icon_name)
			if icon_name_ is not None:
				icon_pixbuf = self.icon_theme.load_icon(icon_name_, icon_size, gtk.ICON_LOOKUP_FORCE_SIZE)

		if icon_pixbuf is None:
			for dir_ in BaseDirectory.xdg_data_dirs:
				for subdir in ('pixmaps', 'icons'):
					path = os.path.join(dir_, subdir, icon_value)
					if os.path.isfile(path):
						icon_pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(path, icon_size, icon_size)

		if icon_pixbuf is None:
			icon_pixbuf = self.icon_theme.load_icon(fallback_icon, icon_size, gtk.ICON_LOOKUP_FORCE_SIZE)

		return gtk.image_new_from_pixbuf(icon_pixbuf)


	def get_icon_name_from_theme(self, icon_name):
		"""
		Find out if this icon exists in the theme (such as 'gtk-open'), or if
		it's a mimetype (such as audio/mpeg, which has an icon audio-mpeg), or
		if it has a generic mime icon (such as audio-x-generic)
		"""

		# replace slashed with dashes for mimetype icons
		icon_name = icon_name.replace('/', '-')

		if self.icon_theme.has_icon(icon_name):
			return icon_name

		# try generic mimetype
		gen_type = icon_name.split('-')[0]
		icon_name = gen_type + '-x-generic'
		if self.icon_theme.has_icon(icon_name):	
			return icon_name

		return None


	def get_icon_name_from_path(self, path):
		"""
		Gets the icon name for a given path using GIO
		"""

		info = None

		try:
			file_ = gio.File(path)
			info = file_.query_info("standard::icon")

		except Exception, exception:
			logging.warn('Could not get icon for %s' % path)
			logging.warn(exception)


		if info is not None:
			icons = info.get_icon().get_property("names")
			for icon_name in icons:
				if self.icon_theme.has_icon(icon_name):
					return icon_name
			
		return None


	def add_tree_to_app_list(self, tree, parent_widget, recursive = True):
		"""
		Adds all the apps in a subtree of Gnome's menu as buttons in a given
		parent widget
		"""

		for node in tree.contents:

			if isinstance(node, gmenu.Entry):

				button = self.add_app_button(node.name, node.icon, parent_widget, 'app', node.desktop_file_path, tooltip = node.get_comment(), app_list = self.app_list)

			elif isinstance(node, gmenu.Directory) and recursive:

				self.add_tree_to_app_list(node, parent_widget)


	def prepare_colors(self):
		"""
		Reads colors from the GTK theme so that the app pane can look like a
		GTK treeview
		"""

		dummy_window = gtk.Window()
		dummy_window.realize()
		app_style = dummy_window.get_style()
		self.style_app_button_bg = app_style.base[gtk.STATE_NORMAL]
		self.style_app_button_fg = app_style.text[gtk.STATE_NORMAL]
		self.get_object('ScrolledViewport').modify_bg(gtk.STATE_NORMAL, self.style_app_button_bg)


	def launch_edit_app(self, *dummy):
		"""
		Opens Gnome's menu editor
		"""

		self.launch_raw('alacarte')


	def on_pin_this_app_clicked(self, widget):
		"""
		Handle the pinning action
		"""

		self.remove_section_from_app_list(self.favorites_section_slab)
		self.clear_pane(self.favorites_section_contents)
		self.settings['pinned items'].append(self.clicked_app)
		self.build_favorites_list(self.favorites_section_slab, 'pinned items')


	def on_unpin_this_app_clicked(self, widget):
		"""
		Handle the unpinning action
		"""

		self.remove_section_from_app_list(self.favorites_section_slab)
		self.clear_pane(self.favorites_section_contents)
		self.settings['pinned items'].remove(self.clicked_app)
		self.build_favorites_list(self.favorites_section_slab, 'pinned items')


	def on_add_to_side_pane_clicked(self, widget):
		"""
		Handle the "add to sidepane" action
		"""

		self.remove_section_from_app_list(self.sidepane_section_slab)
		self.clear_pane(self.sidepane_section_contents)
 		self.clear_pane(self.sidepane)
		self.settings['side pane items'].append(self.clicked_app)
		self.build_favorites_list(self.sidepane_section_slab, 'side pane items')
		self.sidepane.queue_resize() # required! or sidepane's allocation will be x,y,width,0 when first item is added


	def on_remove_from_side_pane_clicked(self, widget):
		"""
		Handle the "remove from sidepane" action
		"""

		self.remove_section_from_app_list(self.sidepane_section_slab)
		self.clear_pane(self.sidepane_section_contents)
 		self.clear_pane(self.sidepane)
		self.settings['side pane items'].remove(self.clicked_app)
		self.build_favorites_list(self.sidepane_section_slab, 'side pane items')


	def on_launch_in_background_pressed(self, widget):
		"""
		Handle the "launch in background" action
		"""

		self.launch_button_command(self.clicked_app, hide = False)


	def on_app_button_button_pressed(self, widget, event):
		"""
		Show context menu for app buttons
		"""

		if event.type != gtk.gdk.BUTTON_PRESS: return

		if  event.button == 2:

			self.launch_button_command(widget.app_info, hide = False)

		elif event.button == 3:

			if widget.app_info['type'] == 'callback': return

			already_pinned = False
			already_on_side_pane = False

			for command in [app['command'] for app in self.settings['pinned items']]:
				if command == widget.app_info['command']: 
					already_pinned = True
					break

			for command in [app['command'] for app in self.settings['side pane items']]:
				if command == widget.app_info['command']: 
					already_on_side_pane = True
					break

			if already_pinned:
				self.pin_menuitem.hide()
				self.unpin_menuitem.show()
			else:
				self.pin_menuitem.show()
				self.unpin_menuitem.hide()

			if already_on_side_pane:
				self.add_side_pane_menuitem.hide()
				self.remove_side_pane_menuitem.show()
			else:
				self.add_side_pane_menuitem.show()
				self.remove_side_pane_menuitem.hide()

			self.clicked_app = widget.app_info

			self.block_focus_out_event()
			self.app_context_menu.popup(None, None, None, event.button, event.time)


	def on_app_button_focused(self, widget, event):
		"""
		Scroll to app buttons when they gain focus
		"""

		alloc = widget.get_allocation()
		scroller_position = self.scroll_adjustment.value
		page_size = self.scroll_adjustment.page_size

		if alloc.y < scroller_position:
			self.scroll_adjustment.set_value(alloc.y)

		elif alloc.y + alloc.height > scroller_position + page_size:
			self.scroll_adjustment.set_value(alloc.y + alloc.height - page_size)


	def on_app_button_clicked(self, widget):
		"""
		Handle the on-click event for buttons on the app list
		"""

		hide = (gtk.get_current_event().state & gtk.gdk.CONTROL_MASK != gtk.gdk.CONTROL_MASK)
		self.launch_button_command(widget.app_info, hide = hide)


	def launch_button_command(self, app_info, hide):
		"""
		Execute app_info['command'], for any app_info['type']
		"""

		command = app_info['command']
		command_type = app_info['type']

		self.opened_last_app_in_background = not hide

		if command_type == 'app':
			self.launch_desktop(command, hide)

		elif command_type == 'raw':
			self.launch_raw(command, hide)

		elif command_type == 'xdg':
			self.launch_xdg(command, hide)

		elif command_type == 'callback':
			text = self.search_entry.get_text().strip()
			if hide: self.hide()
			command(text)


	def launch_desktop(self, command, hide = True):
		"""
		Launch applications represented by .desktop files
		"""

		if os.path.exists(command):

			path = DesktopEntry.DesktopEntry(command).getExec()

			# Strip last part of path if it contains %<a-Z>
			match = self.exec_pattern.match(path)
			
			if match is not None:
				path = match.group(1)

			return self.launch_raw(path, hide)

		else:
			logging.warn('Warning: Tried launching an app that does not exist: %s' % desktop_path)


	def launch_xdg(self, path, hide = True):
		"""
		Open a url, file or folder
		"""

		path = self.escape_quotes(self.unescape(path))
		return self.launch_raw("xdg-open '%s'" % path, hide)


	def launch_raw(self, path, hide = True):
		"""
		Run a command as a subprocess
		"""

		try:
			subprocess.Popen(path, shell = True, cwd = self.home_folder_path)
		except OSError, e:
			logging.error('Could not launch %s' % path)
			logging.error(e)
			return False

		if hide: self.hide()

		return True


	def escape_quotes(self, text):
		"""
		Sanitize a string by escaping quotation marks
		"""

		text = text.replace("'", r"\'")
		text = text.replace('"', r'\"')
		return text


	def unescape(self, text):
		"""
		Clear all sorts of escaping from a URL, like %20 -> [space]
		"""

		return urllib2.unquote(str(text)) # NOTE: it is possible that with python3 we will have to change this line


	def show_all_nonempty_sections(self):
		"""
		Show all sections that currently have search results
		"""

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

		if self.is_searchentry_empty():
			widget.set_sensitive(False)


	def show_lone_section(self, section_slab):
		"""
		Show a single section (because it's been selected in the View pane)
		"""

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
		"""
		Show the "No results to show" text
		"""

		if text is None: text = _('No results to show')

		self.no_results_label.set_text(text)
		self.no_results_slab.show()


	def hide_no_results_text(self):
		"""
		Hide the "No results to show" text
		"""

		self.no_results_slab.hide()


	def consider_showing_no_results_text(self):
		"""
		Decide whether the "No results" text should be shown
		"""

		if self.selected_section is None:

			if self.no_results_to_show:
				self.show_no_results_text()

			return 
			
		if self.section_list[self.selected_section]['has entries']:
			self.selected_section.show()
			self.hide_no_results_text()

		else:
			self.selected_section.hide()
			self.show_no_results_text(_('No results to show in "%(category_name)s"') % {'category_name': self.section_list[self.selected_section]['name']})


	def hide_all_transitory_sections(self, fully_hide = False):
		"""
		Hides all sections that should not appear in the sidebar when
		there is no text in the search entry
		"""

		self.hide_section(self.session_section_slab, fully_hide)
		self.hide_section(self.system_section_slab, fully_hide)
		self.hide_section(self.sidepane_section_slab, fully_hide)
		self.hide_section(self.uncategorized_section_slab, fully_hide)
		
		self.hide_plugin_sections(fully_hide)


	def hide_section(self, section_slab, fully_hide = False):
		"""
		Hide a section slab
		"""

		if fully_hide:
			self.set_section_is_empty(section_slab)

		section_slab.hide()


	def hide_plugin_sections(self, fully_hide = False):
		"""
		Hide the section slabs for all plugins that are marked as transitory
		"""

		for plugin in self.active_plugin_instances:
			if plugin.hide_from_sidebar:
				self.hide_section(plugin.section_slab, fully_hide)


	def show_section(self, section_slab, fully_show = False):
		"""
		Show a section slab
		"""

		if fully_show:
			self.set_section_has_entries(section_slab)

		section_slab.show()


	def set_section_is_empty(self, section_slab):
		"""
		Mark a section as empty (no search results) and hide it
		"""

		self.section_list[section_slab]['has entries'] = False
		self.section_list[section_slab]['category'].hide()


	def set_section_has_entries(self, section_slab):
		"""
		Mark a section as having entries and show it
		"""

		self.section_list[section_slab]['has entries'] = True
		self.section_list[section_slab]['category'].show()


	def set_sidebar_button_active(self, button, state):
		"""
		Toggle a sidebar button
		"""

		if button.get_active() != state:
			self.auto_toggled_sidebar_button = True
			button.set_active(state)


	def scroll_to_top(self):
		"""
		Scroll to the top of the app pane
		"""

		self.scroll_adjustment.set_value(0)



class CardapioPluginInterface:
	# for documentation, see: https://answers.launchpad.net/cardapio/+faq/1172 

	author      = ''
	name        = ''
	description = ''

	# not yet used:
	url         = ''
	help_text   = ''
	version     = ''

	plugin_api_version = 1.2

	search_delay_type = 'local search update delay'

	category_name = ''
	category_icon = ''

	# not yet used:
	category_position = 'end'

	hide_from_sidebar = True

	def __init__(self, settings, write_to_log, handle_search_result, handle_search_error):
		"""
		REQUIRED

		This constructor gets called whenever a plugin is activated.
		(Typically once per session, unless the user is turning plugins on/off)

		The constructor *must* set the instance variable self.loaded to True of False.
		For example, the Tracker plugin sets self.loaded to False if Tracker is not
		installed in the system.

		The constructor is given three parameters:

		   - settings - this is a dict containing the same things that you will
		     find in the config.ini

		   - write_to_log - this is a function that lets you write to Cardapio's
		     log file, like this: write_to_log(self, 'hi there')

		   - handle_search_result - a function to which you should pass the
		     search results when you have them (see more info below, in the 
			 search() method)

		   - handle_search_error - a function to which you should pass an error
		     message if the search fails (see more info below, in the 
			 search() method)

		Note: DO NOT WRITE ANYTHING IN THE settings DICT!!
		"""
		pass


	def __del__(self):
		"""
		NOT REQUIRED

		This destructor gets called whenever a plugin is deactivated
		(Typically once per session, unless the user is turning plugins on/off)
		"""
		pass


	def search(self, text):
		"""
		REQUIRED

		This method gets called when a new text string is entered in the search
		field. One of the following functions should be called from this method
		(of from a thread spawned by this method):

		   * handle_search_result(plugin, results) - if the search goes well
		   * handle_search_error(plugin, text)     - if there is an error

		The arguments to these functions are:

		   * plugin  - this plugin instance (that is, it should always be
		               "self", without quotes)
		   * text    - some text to be inserted in Cardapio's log.
		   * results - an array of dict items as described below.

		item = {
		  'name'      : _('Music'),
		  'tooltip'   : _('Show your Music folder'),
		  'icon name' : 'text-x-generic', 
		  'type'      : 'xdg',
		  'command'   : '~/Music'
		  }

		Where setting 'type' to 'xdg' means that 'command' should be opened
		using xdg-open (you should give it a try it in the terminal, first!).
		Meanwhile, setting 'type' to 'callback' means that 'command' is a
		function that should be called when the item is clicked. This function
		will receive as an argument the current search string.

		Note that you can set item['file name'] to None if you want Cardapio
		to guess the icon from the 'command'. This only works for 'xdg' commands,
		though.
		"""

		pass


	def cancel(self):
		"""
		NOT REQUIRED

		This function should cancel the search operation. This is useful if the search is
		done in a separate thread (which it should, as much as possible)
		"""
		pass


def applet_factory(applet, iid):

	button = gtk.ImageMenuItem()

	cardapio = Cardapio(hidden = True, panel_button = button, panel_applet = applet)

	button.set_tooltip_text(_('Access applications, folders, system settings, etc.'))
	button.set_always_show_image(True)

	menu = gtk.MenuBar()
	menu.set_name('CardapioAppletMenu')
	menu.add(button)

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


import __builtin__
__builtin__._ = _
__builtin__.dbus = dbus
__builtin__.CardapioPluginInterface = CardapioPluginInterface
__builtin__.logging = logging
__builtin__.subprocess = subprocess


