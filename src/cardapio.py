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

# TODO: fix shift-tab from first app widget
# TODO: alt-1, ..., alt-9, alt-0 should activate 1st, ..., 9th, 10th results
# TODO: ctrl-1, ..., ctrl-9, ctrl-0 should activate categories
# TODO: add mount points to "places", allow ejecting from context menu
# TODO: multiple columns when window is wide enough (like gnome-control-center)
# TODO: add "most recent" and "most frequent" with a zeitgeist plugin
# TODO: search results could have context menu with "Open with...", and so on.
# plus other TODO's elsewhere in the code...

try:

	import os
	import re
	import sys
	import gtk
	import gio
	import glib
	import json
	import gmenu
	import urllib2
	import gettext
	import logging
	import keybinder
	import subprocess
	import dbus, dbus.service

	from time import time
	from commands import getoutput
	from pango import ELLIPSIZE_END
	from threading import Lock, Thread
	from locale import setlocale, LC_ALL
	from xdg import BaseDirectory, DesktopEntry
	from dbus.mainloop.glib import DBusGMainLoop
	from distutils.sysconfig import get_python_lib

except Exception, exception:
	print(exception)
	sys.exit(1)

try:
	import gnomeapplet

except:
	# assume that if gnomeapplet is not found then the user is running Cardapio
	# without Gnome (maybe with './cardapio show', for example).
	print('Info: gnomeapplet Python module not present')

try:
	from gnome import execute_terminal_shell as gnome_execute_terminal_shell

except Exception, exception:
	print('Warning: you will not be able to execute scripts in the terminal')
	gnome_execute_terminal_shell = None

try:
	from gnome import program_init as gnome_program_init
	from gnome.ui import master_client as gnome_ui_master_client

except Exception, exception:
	print('Warning: Cardapio will not be able to tell when the session is closed')
	gnome_program_init     = None
	gnome_ui_master_client = None


if gtk.ver < (2, 14, 0):
	print('Error! Gtk version must be at least 2.14. You have version %s' % gtk.ver)
	sys.exit(1)


# Set up translations

# try path like /usr/share/locale
cardapio_path = os.path.dirname(os.path.realpath(__file__))
prefix_path = cardapio_path.split(os.path.sep)[:-2]
prefix_path = [os.path.sep] + prefix_path + ['share', 'locale']
prefix_path = os.path.join(*prefix_path)

# try path like cardapio_path/../locale
if not os.path.exists(prefix_path):
	prefix_path = cardapio_path.split(os.path.sep)[:-1]
	prefix_path = [os.path.sep] + prefix_path + ['locale']
	prefix_path = os.path.join(*prefix_path)

DIR = prefix_path
APP = 'cardapio'

setlocale(LC_ALL, '')
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

	distro_name = getoutput('lsb_release -is')

	min_visibility_toggle_interval = 0.200 # seconds (this is a bit of a hack to fix some focus problems)

	bus_name_str = 'org.varal.Cardapio'
	bus_obj_str  = '/org/varal/Cardapio'

	version = '0.9.151'

	core_plugins = [
			'applications',
			'command_launcher',
			'google',
			'google_localized',
			'pinned',
			'places',
			'software_center',
			'tracker',
			'tracker_fts',
			'zg_recent_documents',
			]

	required_plugins = ['applications', 'places', 'pinned']

	APP_BUTTON      = 0
	CATEGORY_BUTTON = 1
	SESSION_BUTTON  = 2
	SIDEPANE_BUTTON = 3

	REMOTE_PROTOCOLS = ['ftp', 'sftp', 'smb']

	class SafeCardapioProxy:
		pass

	def __init__(self, hidden = False, panel_applet = None, panel_button = None, debug = False):

		self.create_config_folder()
		logging_filename = os.path.join(self.config_folder_path, 'cardapio.log')

		if debug == True: logging_level = logging.DEBUG
		else: logging_level = logging.INFO

		logging_format = r'%(relativeCreated)- 10d %(levelname)- 10s %(message)s'

		logging.basicConfig(filename = logging_filename, level = logging_level, format = logging_format)

		logging.info('----------------- Cardapio launched -----------------')
		logging.info('Cardapio version: %s' % Cardapio.version)
		logging.info('Distribution: %s' % getoutput('lsb_release -ds'))

		self.home_folder_path = os.path.abspath(os.path.expanduser('~'))

		self.read_config_file()

		self.panel_applet                  = panel_applet
		self.panel_button                  = panel_button
		self.last_visibility_toggle        = 0

		self.visible                       = False
		self.app_list                      = []    # used for searching the regular menus
		self.sys_list                      = []    # used for searching the system menus
		self.section_list                  = {}
		self.current_query                 = ''
		self.subfolder_stack               = []
		self.selected_section              = None
		self.no_results_to_show            = False
		self.previously_focused_widget     = None
		self.opened_last_app_in_background = False
		self.auto_toggled_sidebar_button   = False
		self.auto_toggled_view_mode_button = False
		self.focus_out_blocked             = False
		self.clicked_app                   = None
		self.keybinding                    = None
		self.search_timer_local            = None
		self.search_timer_remote           = None
		self.search_timeout_local          = None
		self.search_timeout_remote         = None
		self.plugin_database               = {}
		self.keyword_to_plugin_mapping     = {}
		self.active_plugin_instances       = []
		self.in_system_menu_mode           = False
		self.plugins_still_searching       = 0
		self.bookmark_monitor              = None
		self.volume_monitor                = None

		self.icon_extension_types = re.compile('.*\.(png|xpm|svg)$')

		self.sys_tree = gmenu.lookup_tree('gnomecc.menu')
		self.have_control_center = (self.sys_tree.root is not None)

		if not self.have_control_center:
			self.sys_tree = gmenu.lookup_tree('settings.menu')
			logging.warn('Could not find Control Center menu file. Deactivating Control Center button.')

		self.app_tree = gmenu.lookup_tree('applications.menu')
		self.app_tree.add_monitor(self.on_menu_data_changed)
		self.sys_tree.add_monitor(self.on_menu_data_changed)

		self.package_root = ''
		if __package__ is not None:
			self.package_root = __package__ + '.'

		self.setup_dbus()
		self.setup_base_ui() # must be the first ui-related method to be called
		self.setup_plugins()
		self.build_ui()

		self.schedule_search_with_all_plugins('')

		if not hidden: self.show()

		# this is useful so that the user can edit the config file on first-run
		# without need to quit cardapio first:
		self.save_config_file()

		if gnome_program_init is not None:
			gnome_program_init('', self.version) # Prints a warning to the screen. Ignore it.
			client = gnome_ui_master_client()
			client.connect('save-yourself', self.quit)


	def on_mainwindow_destroy(self, *dummy):
		"""
		Handler for when the Cardapio window is destroyed
		"""

		self.quit()


	def quit(self, *dummy):
		"""
		Saves the current state and quits
		"""

		self.save_config_file()
		self.quit_now()


	def quit_now(self):
		"""
		Quits without saving the current state (usually called if 
		there's an error)
		"""
		logging.info('Exiting...')
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
			return 'Could not import the plugin module'

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

		self.plugin_database['applications'] = {
				'name'              : _('Application menu'),
				'author'            : _('Cardapio Team'),
				'description'       : _('Displays installed applications'),
				'version'           : self.version,
				'category name'     : None,
				'category icon'     : 'applications-other',
				'hide from sidebar' : False,
				'instance'          : None,
				}

		self.plugin_database['places'] = {
				'name'              : _('Places menu'),
				'author'            : _('Cardapio Team'),
				'description'       : _('Displays a list of folders'),
				'version'           : self.version,
				'category name'     : None,
				'category icon'     : 'folder',
				'hide from sidebar' : False,
				'instance'          : None,
				}

		self.plugin_database['pinned'] = {
				'name'              : _('Pinned items'),
				'author'            : _('Cardapio Team'),
				'description'       : _('Displays your favorite items'),
				'version'           : self.version,
				'category name'     : None,
				'category icon'     : 'emblem-favorite',
				'hide from sidebar' : False,
				'instance'          : None,
				}

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
							'name'              : plugin_class.name,
							'author'            : plugin_class.author,
							'description'       : plugin_class.description,
							'version'           : plugin_class.version,
							'category name'     : plugin_class.category_name,
							'category icon'     : plugin_class.category_icon,
							'hide from sidebar' : plugin_class.hide_from_sidebar,
							'instance'          : None,
							}


	def activate_plugins_from_settings(self):
		"""
		Initializes plugins in the database if the user's settings say so.
		"""

		for plugin in self.active_plugin_instances:
			del(plugin)

		self.active_plugin_instances = []
		self.keyword_to_plugin_mapping = {}

		all_plugin_settings = self.settings['plugin settings']

		for basename in self.settings['active plugins']:

			if basename in self.required_plugins: continue

			basename = str(basename)
			plugin_class = self.get_plugin_class(basename)

			if type(plugin_class) is str:
				logging.error('[%s] %s' % (basename, plugin_class))
				self.settings['active plugins'].remove(basename)
				continue

			logging.info('[%s] Initializing...' % basename)

			try:
				plugin = plugin_class(self.safe_cardapio_proxy)

			except Exception, exception:
				logging.error('[%s] Plugin did not load properly: uncaught exception.' % basename)
				logging.error(exception)
				self.settings['active plugins'].remove(basename)
				continue

			if not plugin.loaded:
				self.plugin_write_to_log(plugin, 'Plugin did not load properly')
				self.settings['active plugins'].remove(basename)
				continue

			logging.info('[%s]             ...done!' % basename)

			keyword = plugin.default_keyword
			show_only_with_keyword = False

			if basename in all_plugin_settings:

				plugin_settings = all_plugin_settings[basename]

				if 'keyword' in plugin_settings:
					keyword = plugin_settings['keyword']

				if 'show only with keyword' in plugin_settings:
					show_only_with_keyword = plugin_settings['show only with keyword']

			all_plugin_settings[basename] = {}
			all_plugin_settings[basename]['keyword'] = keyword
			all_plugin_settings[basename]['show only with keyword'] = show_only_with_keyword

			plugin.basename               = basename
			plugin.is_running             = False
			plugin.show_only_with_keyword = show_only_with_keyword

			if plugin.search_delay_type is not None:
				plugin.search_delay_type = plugin.search_delay_type.partition(' search update delay')[0]

			self.active_plugin_instances.append(plugin)
			self.plugin_database[basename]['instance'] = plugin
			self.keyword_to_plugin_mapping[keyword] = plugin


	def plugin_write_to_log(self, plugin, text, is_debug = False, is_warning = False, is_error = False):
		"""
		Writes 'text' to the log file, prefixing it with [plugin name]. Different
		levels of messages can be used by setting one of is_debug, is_warning, is_error:

		debug       - Used for any debugging message, including any messages that may
		              be privacy sensitive. Messages set with the flag is_debug=True
		              will *not* be logged unless the user enters debug mode.

		info        - This is the default level when you don't set any of the flags.
		              Used for things that normal users should see in their logs.

		warning     - Used for reporting things that have gone wrong, but that still
		              allow the plugin to function, even if partially.

		error       - Used for reporting things that have gone wrong, and which do not
		              allow the plugin to function at all.
		"""

		if is_error:
			write = logging.error

		elif is_warning:
			write = logging.warning

		elif is_debug:
			write = logging.debug

		else:
			write = logging.info

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
			self.untoggle_and_show_all_sections()


	def on_sidebar_button_clicked(self, widget, section_slab):
		"""
		Handler for when the user chooses a category in the sidebar
		"""

		if self.auto_toggled_sidebar_button:
			self.auto_toggled_sidebar_button = False
			return True

		if self.selected_section == section_slab:
			self.selected_section = None # necessary!
			self.untoggle_and_show_all_sections()
			return True

		self.toggle_and_show_section(section_slab)


	def on_sidebar_button_hovered(self, widget):
		"""
		Handler for when the user hovers over a category in the sidebar
		"""

		widget.set_active(True)


	def create_config_folder(self):
		"""
		Creates Cardapio's config folder (usually at ~/.config/Cardapio)
		"""

		self.config_folder_path = os.path.join(DesktopEntry.xdg_config_home, 'Cardapio')

		if not os.path.exists(self.config_folder_path):
			os.mkdir(self.config_folder_path)

		elif not os.path.isdir(self.config_folder_path):
			logging.error('Error! Cannot create folder "%s" because a file with that name already exists!' % self.config_folder_path)
			self.quit_now()


	def get_config_file(self, mode):
		"""
		Returns a file handler to Cardapio's config file.
		"""

		config_file_path = os.path.join(self.config_folder_path, 'config.ini')

		if not os.path.exists(config_file_path):
			open(config_file_path, 'w+')

		elif not os.path.isfile(config_file_path):
			logging.error('Error! Cannot create file "%s" because a folder with that name already exists!' % config_file_path)
			self.quit_now()

		try:
			config_file = open(config_file_path, mode)

		except Exception, exception:
			logging.error('Could not read config file "%s":' % config_file_path)
			logging.error(exception)
			config_file = None

		return config_file


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
			logging.error('Could not read config file:')
			logging.error(exception)

		finally:
			config_file.close()

		default_side_pane_items = []
		path = getoutput('which software-center')
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
		self.read_config_option(s, 'splitter position'          , 0                        ) # int, position in pixels
		self.read_config_option(s, 'show session buttons'       , False                    ) # bool
		self.read_config_option(s, 'keep search results'        , False                    ) # bool
		self.read_config_option(s, 'open on hover'              , False                    ) # bool
		self.read_config_option(s, 'open categories on hover'   , False                    ) # bool
		self.read_config_option(s, 'min search string length'   , 3                        ) # int, number of characters
		self.read_config_option(s, 'menu rebuild delay'         , 5                        , force_update_from_version = [0,9,96]) # seconds
		self.read_config_option(s, 'search results limit'       , 5                        ) # int, number of results
		self.read_config_option(s, 'long search results limit'  , 15                       ) # int, number of results
		self.read_config_option(s, 'local search update delay'  , 100                      , force_update_from_version = [0,9,96]) # msec
		self.read_config_option(s, 'remote search update delay' , 250                      , force_update_from_version = [0,9,96]) # msec
		self.read_config_option(s, 'local search timeout'       , 3000                     ) # msec
		self.read_config_option(s, 'remote search timeout'      , 5000                     ) # msec
		self.read_config_option(s, 'autohide delay'             , 250                      ) # msec
		self.read_config_option(s, 'keybinding'                 , '<Super>space'           ) # the user should use gtk.accelerator_parse('<Super>space') to see if the string is correct!
		self.read_config_option(s, 'applet label'               , _('Menu')                ) # string
		self.read_config_option(s, 'applet icon'                , 'start-here'             , override_empty_str = True) # string (either a path to the icon, or an icon name)
		self.read_config_option(s, 'pinned items'               , []                       )
		self.read_config_option(s, 'side pane items'            , default_side_pane_items  )
		self.read_config_option(s, 'active plugins'             , ['pinned', 'places', 'applications', 'tracker', 'google', 'command_launcher', 'software_center'])
		self.read_config_option(s, 'plugin settings'            , {}                       )

		# these are a bit of a hack:
		self.read_config_option(s, 'handler for ftp paths'      , r"nautilus '%s'"         ) # a command line using %s
		self.read_config_option(s, 'handler for sftp paths'     , r"nautilus '%s'"         ) # a command line using %s
		self.read_config_option(s, 'handler for smb paths'      , r"nautilus '%s'"         ) # a command line using %s
		# (see https://bugs.launchpad.net/bugs/593141)

		self.settings['cardapio version'] = self.version


		# clean up the config file whenever options are changed between versions

		# 'side pane' used to be called 'system pane'
		if 'system pane' in self.settings:
			self.settings['side pane'] = self.settings['system pane']
			self.settings.pop('system pane')

		# 'None' used to be the 'applications' plugin
		if None in self.settings['active plugins']:
			i = self.settings['active plugins'].index(None)
			self.settings['active plugins'][i] = 'applications'

		# make sure required plugins are in the plugin list
		for required_plugin in self.required_plugins:

			if required_plugin not in self.settings['active plugins']:
				self.settings['active plugins'] = [required_plugin] + self.settings['active plugins']

		# make sure plugins only appear once in the plugin list
		for plugin_name in self.settings['active plugins']:

			while len([basename for basename in self.settings['active plugins'] if basename == plugin_name]) > 1:
				self.settings['active plugins'].remove(plugin_name)


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
				settings_version = [int(i) for i in user_settings['cardapio version'].split('.')]

			else:
				settings_version = 0

			if settings_version <= force_update_from_version:

				self.settings[key] = val


	def save_config_file(self):
		"""
		Saves the self.settings dict into the config file
		"""

		config_file = self.get_config_file('w')

		if config_file is None:
			logging.error('Could not load config file for saving settings')
			return

		logging.info('Saving config file...')
		json.dump(self.settings, config_file, sort_keys = True, indent = 4)
		logging.info('                  ...done!')


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

		self.get_object = self.builder.get_object
		self.window                    = self.get_object('CardapioWindow')
		self.message_window            = self.get_object('MessageWindow')
		self.about_dialog              = self.get_object('AboutDialog')
		self.options_dialog            = self.get_object('OptionsDialog')
		self.executable_file_dialog    = self.get_object('ExecutableFileDialog')
		self.application_pane          = self.get_object('ApplicationPane')
		self.category_pane             = self.get_object('CategoryPane')
		self.system_category_pane      = self.get_object('SystemCategoryPane')
		self.sidepane                  = self.get_object('SideappPane')
		self.search_entry              = self.get_object('SearchEntry')
		self.scrolled_window           = self.get_object('ScrolledWindow')
		self.scroll_adjustment         = self.scrolled_window.get_vadjustment()
		self.session_pane              = self.get_object('SessionPane')
		self.left_session_pane         = self.get_object('LeftSessionPane')
		self.right_session_pane        = self.get_object('RightSessionPane')
		self.context_menu              = self.get_object('CardapioContextMenu')
		self.app_context_menu          = self.get_object('AppContextMenu')
		self.app_menu_separator        = self.get_object('AppMenuSeparator')
		self.pin_menuitem              = self.get_object('PinMenuItem')
		self.unpin_menuitem            = self.get_object('UnpinMenuItem')
		self.add_side_pane_menuitem    = self.get_object('AddSidePaneMenuItem')
		self.remove_side_pane_menuitem = self.get_object('RemoveSidePaneMenuItem')
		self.open_folder_menuitem      = self.get_object('OpenParentFolderMenuItem')
		self.peek_inside_menuitem      = self.get_object('PeekInsideMenuItem')
		self.eject_menuitem            = self.get_object('EjectMenuItem')
		self.plugin_tree_model         = self.get_object('PluginListstore')
		self.plugin_checkbox_column    = self.get_object('PluginCheckboxColumn')
		self.view_mode_button          = self.get_object('ViewModeButton')

		# HACK: fix names of widgets to allow theming
		# (glade doesn't seem to properly add names to widgets anymore...)
		for widget in self.builder.get_objects():

			# skip the about dialog or the app name will be overwritten!
			if widget == self.about_dialog: continue

			if 'set_name' in dir(widget):
				widget.set_name(gtk.Buildable.get_name(widget))

		self.icon_theme = gtk.icon_theme_get_default()

		uninstalled_icon_path = '/usr/share/app-install/icons/'
		if os.path.exists(uninstalled_icon_path):
			self.icon_theme.append_search_path(uninstalled_icon_path)

		self.icon_theme.connect('changed', self.on_icon_theme_changed)
		self.icon_size_app = gtk.icon_size_lookup(gtk.ICON_SIZE_LARGE_TOOLBAR)[0]
		self.icon_size_category = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)[0]
		self.icon_size_menu = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)[0]
		self.drag_allowed_cursor = gtk.gdk.Cursor(gtk.gdk.FLEUR)

		self.section_label_attributes = self.get_object('SectionName').get_attributes()

		# make sure buttons have icons!
		self.gtk_settings = gtk.settings_get_default()
		self.gtk_settings.set_property('gtk-button-images', True)
		self.gtk_settings.connect('notify', self.on_gtk_settings_changed)

		self.window.set_keep_above(True)

		# make edges draggable
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


	def setup_plugins(self):
		"""
		Reads all plugins from the plugin folders and activates the ones that
		have been specified in the settings file.
		"""

		self.safe_cardapio_proxy = Cardapio.SafeCardapioProxy()
		self.safe_cardapio_proxy.settings = self.settings
		self.safe_cardapio_proxy.write_to_log = self.plugin_write_to_log
		self.safe_cardapio_proxy.handle_search_result = self.plugin_handle_search_result
		self.safe_cardapio_proxy.handle_search_error = self.plugin_handle_search_error
		self.safe_cardapio_proxy.ask_for_reload_permission = self.plugin_ask_for_reload_permission

		self.build_plugin_database()
		self.activate_plugins_from_settings()


	def get_best_icon_size_for_panel(self):
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

			if abs(icon_size_pixels - panel_size) <= 1:
				return icon_size_pixels

		# if no stock icon size if close enough, then use the panel size
		return panel_size


	def setup_panel_button(self):
		"""
		Sets up the look and feel of the Cardapio applet button
		"""

		label_text = self.settings['applet label']
		self.panel_button.set_label(label_text)
		button_icon_pixbuf = self.get_icon_pixbuf(self.settings['applet icon'], self.get_best_icon_size_for_panel(), 'distributor-logo')
		button_icon = gtk.image_new_from_pixbuf(button_icon_pixbuf)
		self.panel_button.set_image(button_icon)

		if label_text:
			clean_imagemenuitem = gtk.ImageMenuItem()
			default_spacing = clean_imagemenuitem.style_get_property('toggle-spacing')

			gtk.rc_parse_string('''
				style "cardapio-applet-style-with-space"
				{
					GtkImageMenuItem::toggle-spacing = %d
				}
				widget "*CardapioApplet" style:application "cardapio-applet-style-with-space"
				''' % default_spacing)
		else:
			gtk.rc_parse_string('''
				style "cardapio-applet-style-no-space"
				{
					GtkImageMenuItem::toggle-spacing = 0
				}
				widget "*CardapioApplet" style:application "cardapio-applet-style-no-space"
				''')

		# apparently this happens sometimes (maybe when the parent isn't realized yet?)
		if self.panel_button.parent is None: return

		menubar = self.panel_button.parent 
		menubar.remove(self.panel_button)
		menubar.add(self.panel_button)

		menubar.connect('button-press-event', self.on_panel_button_pressed)

		if 'applet_press_handler' in dir(self):
			try:
				self.panel_button.disconnect(self.applet_press_handler)
				self.panel_button.disconnect(self.applet_enter_handler)
				self.panel_button.disconnect(self.applet_leave_handler)
			except: pass

		if self.settings['open on hover']:
			self.applet_press_handler = self.panel_button.connect('button-press-event', self.on_panel_button_toggled, True)
			self.applet_enter_handler = self.panel_button.connect('enter-notify-event', self.on_applet_cursor_enter)
			self.applet_leave_handler = self.panel_button.connect('leave-notify-event', self.on_mainwindow_cursor_leave)

		else:
			self.applet_press_handler = self.panel_button.connect('button-press-event', self.on_panel_button_toggled, False)
			self.applet_enter_handler = self.panel_button.connect('enter-notify-event', return_true)
			self.applet_leave_handler = self.panel_button.connect('leave-notify-event', return_true)


	def setup_ui_from_all_settings(self):
		"""
		Setup UI elements according to user preferences
		"""

		self.setup_ui_from_gui_settings()
		self.restore_dimensions()


	def setup_ui_from_gui_settings(self):
		"""
		Setup UI elements from the set of preferences that are accessible
		from the options dialog.
		"""

		if self.keybinding is not None:
			try: keybinder.unbind(self.keybinding)
			except: pass

		self.keybinding = self.settings['keybinding']
		keybinder.bind(self.keybinding, self.show_hide)

		if self.panel_button is not None:
			self.setup_panel_button()

		if self.settings['show session buttons']:
			self.session_pane.show()
		else:
			self.session_pane.hide()

		# set up open-on-hover for categories

		category_buttons = self.category_pane.get_children() + self.system_category_pane.get_children()

		if self.settings['open categories on hover']:
			for category_button in category_buttons:

				if 'has_hover_handler' in dir(category_button) and not category_button.has_hover_handler: # is there a better way to check this?
					category_button.handler_unblock_by_func(self.on_sidebar_button_hovered)
				else: 
					category_button.connect('enter', self.on_sidebar_button_hovered)
					category_button.has_hover_handler = True 

		else:
			for category_button in category_buttons:
				if 'has_hover_handler' in dir(category_button) and category_button.has_hover_handler:
					category_button.handler_block_by_func(self.on_sidebar_button_hovered)
					category_button.has_hover_handler = False


	def build_ui(self):
		"""
		Read the contents of all menus and plugins and build the UI
		elements that support them.
		"""

		self.no_results_text             = _('No results to show')
		self.no_results_in_category_text = _('No results to show in "%(category_name)s"')
		self.plugin_loading_text         = _('Searching...')
		self.plugin_timeout_text         = _('Search timed out')

		self.read_gtk_theme_info()

		self.app_list              = []  # holds a list of all apps for searching purposes
		self.sys_list              = []  # holds a list of all apps in the system menus
		self.section_list          = {}  # holds a list of all sections to allow us to reference them by their "slab" widgets

		self.clear_pane(self.application_pane)
		self.clear_pane(self.category_pane)
		self.clear_pane(self.system_category_pane)
		self.clear_pane(self.sidepane)
		self.clear_pane(self.left_session_pane)
		self.clear_pane(self.right_session_pane)

		self.current_query         = ''
		self.subfolder_stack       = []

		# "All" button for the regular menu
		button = self.add_button(_('All'), None, self.category_pane, tooltip = _('Show all categories'), button_type = Cardapio.CATEGORY_BUTTON)
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_sections_sidebar_button = button
		self.set_sidebar_button_active(button, True)
		self.all_sections_sidebar_button.set_sensitive(False)

		# "All" button for the system menu
		button = self.add_button(_('All'), None, self.system_category_pane, tooltip = _('Show all categories'), button_type = Cardapio.CATEGORY_BUTTON)
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_system_sections_sidebar_button = button
		self.set_sidebar_button_active(button, True)
		self.all_system_sections_sidebar_button.set_sensitive(False)

		self.no_results_slab, dummy, self.no_results_label = self.add_application_section('Dummy text')
		self.hide_no_results_text()

		if self.panel_applet is None:
			self.get_object('AppletOptionPane').hide()

		if not self.have_control_center:
			self.view_mode_button.hide()

		self.add_subfolders_slab()
		self.add_all_reorderable_slabs()

		self.build_places_list()
		self.build_session_list()
		self.build_system_list()
		self.build_uncategorized_list()
		self.build_favorites_list(self.favorites_section_slab, 'pinned items')
		self.build_favorites_list(self.sidepane_section_slab, 'side pane items')

		self.setup_ui_from_all_settings()
		self.set_message_window_visible(False)


	def rebuild_ui(self, show_message = False):
		"""
		Rebuild the UI after a timer (this is called when the menu data changes,
		for example)
		"""

		logging.info('Rebuilding UI')

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)
			self.rebuild_timer = None

		if show_message:
			self.set_message_window_visible(True)

		self.build_ui()

		for plugin in self.active_plugin_instances:
			glib.idle_add(plugin.on_reload_permission_granted)

		self.schedule_search_with_all_plugins('')


	def show_executable_file_dialog(self, path):
		"""
		Opens a dialog similar to the one in Nautilus, that asks whether an
		executable script should be launched or edited.
		"""

		basename = os.path.basename(path)
		arg_dict = {'file_name': basename}

		primary_text = '<big><b>' + _('Do you want to run "%(file_name)s" or display its contents?' % arg_dict) + '</b></big>'
		secondary_text = _('"%(file_name)s" is an executable text file.' % arg_dict)

		self.get_object('ExecutableDialogPrimaryText').set_markup(primary_text)
		self.get_object('ExecutableDialogSecondaryText').set_text(secondary_text)

		if gnome_execute_terminal_shell is None:
			self.get_object('ExecutableDialogRunInTerminal').hide()

		self.executable_file_dialog.set_focus(self.get_object('ExecutableDialogCancel'))

		response = self.executable_file_dialog.run()
		self.executable_file_dialog.hide()

		return response


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


	def on_dialog_close(self, dialog, response = None):
		"""
		Handler for when a dialog's X button is clicked
		"""

		dialog.hide()
		return True


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
		self.set_widget_from_option('OptionKeepResults', 'keep search results')
		self.set_widget_from_option('OptionOpenOnHover', 'open on hover')
		self.set_widget_from_option('OptionOpenCategoriesOnHover', 'open categories on hover')

		icon_size = gtk.icon_size_lookup(4)[0] # 4 because it's that same as in the UI file

		self.plugin_tree_model.clear()

		# place active plugins at the top of the list, in order
		plugin_list = []
		plugin_list += [basename for basename in self.settings['active plugins']]
		plugin_list += [basename for basename in self.plugin_database if basename not in plugin_list]

		for basename in plugin_list:

			plugin_info = self.plugin_database[basename]
			name = plugin_info['name']

			is_active   = (basename in self.settings['active plugins'])
			is_core     = (basename in self.core_plugins)
			is_required = (basename in self.required_plugins)

			if is_required : title = '<b>%s</b>' % name

			icon_pixbuf = self.get_icon_pixbuf(plugin_info['category icon'], icon_size, 'package-x-generic')

			self.plugin_tree_model.append([basename, name, name, is_active, is_core, not is_required, icon_pixbuf])

		self.update_plugin_description()
		self.options_dialog.show()


	def close_options_dialog(self, *dummy):
		"""
		Hides the Options Dialog
		"""

		self.options_dialog.hide()
		self.save_config_file()
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
		self.settings['keep search results'] = self.get_object('OptionKeepResults').get_active()
		self.settings['open on hover'] = self.get_object('OptionOpenOnHover').get_active()
		self.settings['open categories on hover'] = self.get_object('OptionOpenCategoriesOnHover').get_active()
		self.setup_ui_from_gui_settings()


	def update_plugin_description(self, *dummy):
		"""
		Writes information about the currently-selected plugin on the GUI
		"""

		model, iter_ = self.get_object('PluginTreeView').get_selection().get_selected()

		if iter_ is None:
			is_core = True
			plugin_info = {'name': '', 'version': '', 'author': '', 'description': ''}

		else:
			is_core  = self.plugin_tree_model.get_value(iter_, 4)
			basename = self.plugin_tree_model.get_value(iter_, 0)
			plugin_info = self.plugin_database[basename]

		description = _('<b>Plugin:</b> %(name)s %(version)s\n<b>Author:</b> %(author)s\n<b>Description:</b> %(description)s') % plugin_info
		if not is_core  : description += '\n<small>(' + _('This is a community-supported plugin') + ')</small>'

		label = self.get_object('OptionPluginInfo')
		dummy, dummy, width, dummy = label.get_allocation()
		label.set_markup(description)
		label.set_line_wrap(True)

		# make sure the label doesn't resize the window!
		if width > 1:
			label.set_size_request(width - self.scrollbar_width - 20, -1)

		# The -20 is a hack because some themes add extra padding that I need to
		# account for. Since I don't know where that padding is comming from, I
		# just enter a value (20px) that is larger than I assume any theme would
		# ever use.


	def apply_plugins_from_option_window(self, *dummy):
		"""
		Handler for when the user clicks on "Apply" in the plugin tab of the
		Options Dialog
		"""

		self.settings['active plugins'] = []
		iter_ = self.plugin_tree_model.get_iter_first()

		while iter_ is not None:

			if self.plugin_tree_model.get_value(iter_, 3):
				self.settings['active plugins'].append(self.plugin_tree_model.get_value(iter_, 0))

			iter_ = self.plugin_tree_model.iter_next(iter_)

		self.options_dialog.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))

		# ensure cursor is rendered immediately
		gtk.gdk.flush()
		while gtk.events_pending():
			gtk.main_iteration()

		self.activate_plugins_from_settings()
		self.options_dialog.window.set_cursor(None)

		self.schedule_rebuild()


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


	def on_plugin_state_toggled(self, cell, path):
		"""
		Believe it or not, GTK requires you to manually tell the checkbuttons
		that reside within a tree to toggle when the user clicks on them.
		This function does that.
		"""

		iter_ = self.plugin_tree_model.get_iter(path)
		basename = self.plugin_tree_model.get_value(iter_, 0)

		if basename in self.required_plugins: return

		self.plugin_tree_model.set_value(iter_, 3, not cell.get_active())
		self.apply_plugins_from_option_window()


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
			self.window.handler_block_by_func(self.on_mainwindow_cursor_leave)
			self.focus_out_blocked = True


	def unblock_focus_out_event(self, *dummy):
		"""
		If the focus-out event was previously blocked, this unblocks it
		"""

		if self.focus_out_blocked:
			self.window.handler_unblock_by_func(self.on_mainwindow_focus_out)
			self.window.handler_unblock_by_func(self.on_mainwindow_cursor_leave)
			self.focus_out_blocked = False


	def on_mainwindow_after_key_pressed(self, widget, event):
		"""
		Send all keypresses to the search entry, so the user can search
		from anywhere without the need to focus the search entry first
		"""

		w = self.window.get_focus()

		if w != self.search_entry and w == self.previously_focused_widget:

			if event.is_modifier: return

			self.window.set_focus(self.search_entry)
			self.search_entry.set_position(len(self.search_entry.get_text()))
			self.search_entry.emit('key-press-event', event)

		else:
			self.previously_focused_widget = None


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

		self.save_dimensions()

		if self.panel_applet is not None:

			cursor_x, cursor_y, dummy = self.panel_applet.window.get_pointer()
			dummy, dummy, applet_w, applet_h = self.panel_applet.get_allocation()

			# Make sure clicking the applet button doesn't cause a focus-out event.
			# Otherwise, the click signal actually happens *after* the focus-out,
			# which causes the applet to be re-shown rather than disappearing.
			# So by ignoring this focus-out we actually make sure that Cardapio
			# will be hidden after all. Silly.

			if self.panel_applet is not None and (0 <= cursor_x <= applet_w and 0 <= cursor_y <= applet_h):
				return

		# If the last app was opened in the background, make sure Cardapio
		# doesn't hide when the app gets focused

		if self.opened_last_app_in_background:

			self.opened_last_app_in_background = False
			self.show_window_on_top(self.window)
			return

		self.hide()


	def on_applet_cursor_enter(self, widget, event):
		"""
		Handler for when the cursor enters the panel applet.
		"""

		self.show_hide()
		return True


	def on_mainwindow_cursor_leave(self, widget, event):
		"""
		Handler for when the cursor leaves the Cardapio window.
		If using 'open on hover', this hides the Cardapio window after a delay.
		"""

		if self.settings['open on hover']:
			glib.timeout_add(self.settings['autohide delay'], self.hide_if_mouse_away)
			self.save_dimensions()


	def on_mainwindow_delete_event(self, widget, event):
		"""
		What happens when the user presses Alt-F4? If in panel mode,
		nothing. If in launcher mode, this terminates Cardapio.
		"""

		if self.panel_applet:
			# keep window alive if in panel mode
			return True


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
			self.read_gtk_theme_info()
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


	def on_view_mode_toggled(self, widget):
		"""
		Handler for when the "system menu" button is toggled
		"""

		if self.auto_toggled_view_mode_button:
			self.auto_toggled_view_mode_button = False
			return True

		self.switch_modes(show_system_menus = widget.get_active())


	def switch_modes(self, show_system_menus, toggle_mode_button = False):
		"""
		Switched between "all menus" and "system menus" mode
		"""

		self.in_system_menu_mode = show_system_menus

		if toggle_mode_button:
			if self.view_mode_button.get_active() != show_system_menus:
				self.auto_toggled_view_mode_button = True
				self.view_mode_button.set_active(show_system_menus)

		self.untoggle_and_show_all_sections()
		self.on_search_entry_changed()

		if show_system_menus:
			self.category_pane.hide()
			self.system_category_pane.show()

		else:
			self.system_category_pane.hide()
			self.category_pane.show()


	def on_search_entry_icon_pressed(self, widget, iconpos, event):
		"""
		Handler for when the "clear" icon of the search entry is pressed
		"""

		if self.is_search_entry_empty():
			self.untoggle_and_show_all_sections()

		else:
			self.clear_search_entry()


	def on_search_entry_changed(self, *dummy):
		"""
		Handler for when the user types something in the search entry
		"""

		text = self.search_entry.get_text().strip()

		if text and text == self.current_query: return
		self.current_query = text

		self.no_results_to_show = True
		self.hide_no_results_text()

		handled = False
		in_subfolder_search_mode = (text and text.find('/') != -1)

		if not in_subfolder_search_mode:
			self.fully_hide_all_sections()
			self.subfolder_stack = []

		if self.in_system_menu_mode:
			self.search_menus(text, self.sys_list)
			handled = True

		elif text and text[0] == '?':
			keyword, dummy, text = text.partition(' ')
			self.current_query = text

			if len(keyword) >= 1 and text:
				self.search_with_plugin_keyword(keyword[1:], text)

			self.consider_showing_no_results_text()
			handled = True

		elif in_subfolder_search_mode:
			first_app_widget = self.get_first_visible_app()
			selected_app_widget = self.get_selected_app()
			self.fully_hide_all_sections()
			self.previously_focused_widget = None
			handled = self.search_subfolders(text, first_app_widget, selected_app_widget)

		if not handled:
			self.search_menus(text, self.app_list)
			self.schedule_search_with_all_plugins(text)

			if len(text) < self.settings['min search string length']:
				for plugin in self.active_plugin_instances:
					if plugin.hide_from_sidebar:
						self.set_section_is_empty(plugin.section_slab)
						plugin.section_slab.hide()

		if len(text) == 0:
			self.hide_all_transitory_sections(fully_hide = True)
		else:
			self.all_sections_sidebar_button.set_sensitive(True)
			self.all_system_sections_sidebar_button.set_sensitive(True)

		self.consider_showing_no_results_text()


	def search_menus(self, text, app_list):
		"""
		Start a menu search
		"""

		text = text.lower()

		self.application_pane.hide() # for speed

		for app in app_list:

			if app['name'].find(text) == -1 and app['basename'].find(text) == -1:
				app['button'].hide()
			else:
				app['button'].show()
				self.set_section_has_entries(app['section'])
				self.no_results_to_show = False

		if self.selected_section is None:
			self.untoggle_and_show_all_sections()

		self.application_pane.show() # restore application_pane


	def create_subfolder_stack(self, path):
		"""
		Fills in the subfolder_stack array with all ancestors of a given path
		"""

		path = '/' + path.strip('/')
		self.subfolder_stack = [('', '/')]

		i = 0
		while True:
			i = path.find('/', i+1)
			if i == -1: break
			partial_path = path[:i]
			self.subfolder_stack.append((partial_path, partial_path))

		self.subfolder_stack.append((path, path))


	def search_subfolders(self, text, first_app_widget, selected_app_widget):
		"""
		Lets you browse your filesystem through Cardapio by typing slash "/" after
		a search query to "push into" a folder. 
		"""

		search_inside = (text[-1] == '/')
		slash_pos     = text.rfind('/')
		base_text     = text[slash_pos+1:]
		path          = None

		self.subfolders_section_slab.hide() # for added performance
		self.clear_pane(self.subfolders_section_contents)

		if not search_inside:
			if not self.subfolder_stack: return False
			slash_count = text.count('/')
			path = self.subfolder_stack[slash_count - 1][1]
			self.subfolder_stack = self.subfolder_stack[:slash_count]

		else:
			text = text[:-1]
			curr_level = text.count('/')

			if self.subfolder_stack:
				prev_level = self.subfolder_stack[-1][0].count('/')
			else: 
				prev_level = -1

			# if typed root folder
			if text == '': 
				path        = '/'
				base_text   = ''
				self.subfolder_stack = [(text, path)]

			# if pushing into a folder
			elif prev_level < curr_level:

				if first_app_widget is not None:
					if selected_app_widget is not None: widget = selected_app_widget
					else: widget = first_app_widget

					if widget.app_info['type'] != 'xdg': return False
					path = self.escape_quotes(self.unescape(widget.app_info['command']))

					path_type, path = urllib2.splittype(path)
					if path_type and path_type != 'file': return False
					if not os.path.isdir(path): return False
					self.subfolder_stack.append((text, path))

			# if popping out of a folder
			else:
				if prev_level > curr_level: self.subfolder_stack.pop()
				path = self.subfolder_stack[-1][1]

		if path is None: return False

		if path == '/': parent_name = _('Filesystem Root')
		else: dummy, parent_name = os.path.split(path)
		self.subfolders_label.set_text(parent_name)

		count = 0
		limit = self.settings['long search results limit']
		base_text = base_text.lower()
		
		for filename in os.listdir(path):

			# ignore hidden files
			if filename[0] == '.': continue

			if base_text and filename.lower().find(base_text) == -1: continue

			if count >= limit: break
			count += 1

			command = os.path.join(path, filename)
			icon_name = self.get_icon_name_from_path(command)
			if icon_name is None: icon_name = 'folder'

			basename, dummy = os.path.splitext(filename)
			button = self.add_app_button(filename, icon_name, self.subfolders_section_contents, 'xdg', command, tooltip = command, app_list = None)

		if count:
			self.subfolders_section_slab.show()
			self.set_section_has_entries(self.subfolders_section_slab)
			self.no_results_to_show = False

		else:
			self.no_results_to_show = True

		return True


	def cancel_all_plugin_timers(self):
		"""
		Cancels both the "search start"-type timers and the "search timeout"-type ones
		"""

		if self.search_timer_local is not None:
			glib.source_remove(self.search_timer_local)

		if self.search_timer_remote is not None:
			glib.source_remove(self.search_timer_remote)

		if self.search_timeout_local is not None:
			glib.source_remove(self.search_timeout_local)

		if self.search_timeout_remote is not None:
			glib.source_remove(self.search_timeout_remote)


	def search_with_plugin_keyword(self, keyword, text):
		"""
		Search using the plugin that matches the given keyword
		"""

		if not keyword: return

		keyword_exists = False

		# search for a registered keyword that has this keyword as a substring
		for plugin_keyword in self.keyword_to_plugin_mapping:
			if plugin_keyword.find(keyword) == 0:
				keyword_exists = True
				keyword = plugin_keyword
				break

		if not keyword_exists: return

		plugin = self.keyword_to_plugin_mapping[keyword]

		self.cancel_all_plugins()
		self.cancel_all_plugin_timers()

		self.schedule_search_with_specific_plugin(text, plugin.search_delay_type, plugin)


	def schedule_search_with_all_plugins(self, text):
		"""
		Cleans up plugins and timers, and creates new timers to search with all
		plugins
		"""

		self.cancel_all_plugins()
		self.cancel_all_plugin_timers()

		self.schedule_search_with_specific_plugin(text, None)
		self.schedule_search_with_specific_plugin(text, 'local')
		self.schedule_search_with_specific_plugin(text, 'remote')


	def schedule_search_with_specific_plugin(self, text, delay_type = None, specific_plugin = None):
		"""
		Sets up timers to start searching with the plugins specified by the
		delay_type and possibly by "specific_plugin"
		"""

		if delay_type is None:
			self.search_with_specific_plugin(text, None, specific_plugin)

		elif delay_type == 'local':
			timer_delay = self.settings['local search update delay']
			timeout     = self.settings['local search timeout']
			self.search_timer_local   = glib.timeout_add(timer_delay, self.search_with_specific_plugin, text, delay_type, specific_plugin)
			self.search_timeout_local = glib.timeout_add(timeout, self.show_all_plugin_timeout_text, delay_type)
		
		else:
			timer_delay = self.settings['remote search update delay']
			timeout     = self.settings['remote search timeout']
			self.search_timer_remote   = glib.timeout_add(timer_delay, self.search_with_specific_plugin, text, delay_type, specific_plugin)
			self.search_timeout_remote = glib.timeout_add(timeout, self.show_all_plugin_timeout_text, delay_type)


	def search_with_specific_plugin(self, text, delay_type, specific_plugin = None):
		"""
		Start a plugin-based search
		"""

		if delay_type == 'local':
			if self.search_timer_local is not None:
				glib.source_remove(self.search_timer_local)
				self.search_timer_local = None

		elif delay_type == 'remote':
			if self.search_timer_remote is not None:
				glib.source_remove(self.search_timer_remote)
				self.search_timer_remote = None

		if specific_plugin is not None:

			plugin = specific_plugin
			plugin.is_running = True

			try:
				self.show_plugin_loading_text(plugin)
				plugin.search(text, self.settings['long search results limit'])

			except Exception, exception:
				self.plugin_write_to_log(plugin, 'Plugin search query failed to execute', is_error = True)
				logging.error(exception)

			return False # Required!

		text_is_too_small = (len(text) < self.settings['min search string length'])
		number_of_results = self.settings['search results limit']

		for plugin in self.active_plugin_instances:

			if plugin.search_delay_type != delay_type or plugin.show_only_with_keyword:
				continue

			if plugin.hide_from_sidebar and text_is_too_small:
				continue

			plugin.is_running = True

			try:
				self.show_plugin_loading_text(plugin)
				plugin.search(text, number_of_results)

			except Exception, exception:
				self.plugin_write_to_log(plugin, 'Plugin search query failed to execute', is_error = True)
				logging.error(exception)

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def reset_plugin_section_contents(self, plugin):
		"""
		Clear the contents of a plugin's slab, usually to fill it with results later
		"""

		container = plugin.section_contents.parent

		if container is None:
			# plugin was deactivated while waiting for search result
			return False

		container.remove(plugin.section_contents)
		plugin.section_contents = gtk.VBox()
		container.add(plugin.section_contents)

		return True


	def show_plugin_loading_text(self, plugin):
		"""
		Write "Searching..." under the plugin slab title
		"""

		self.reset_plugin_section_contents(plugin)
		label = gtk.Label(self.plugin_loading_text)
		label.set_alignment(0, 0.5)
		label.set_sensitive(False)
		label.show()

		plugin.section_contents.pack_start(label, expand = False, fill = False)
		plugin.section_contents.show()

		if self.selected_section is None or plugin.section_slab == self.selected_section:
			plugin.section_slab.show()
			self.hide_no_results_text()

		self.plugins_still_searching += 1


	def show_all_plugin_timeout_text(self, delay_type):
		"""
		Write "Plugin timed out..." under the plugin slab title
		"""

		for plugin in self.active_plugin_instances:

			if not plugin.is_running: continue
			if plugin.search_delay_type != delay_type: continue

			try:
				plugin.cancel()

			except Exception, exception:
				self.plugin_write_to_log(plugin, 'Plugin failed to cancel query', is_error = True)
				logging.error(exception)

			self.reset_plugin_section_contents(plugin)
			label = gtk.Label(self.plugin_timeout_text)
			label.set_alignment(0, 0.5)
			label.set_sensitive(False)
			label.show()

			plugin.section_contents.pack_start(label, expand = False, fill = False)
			plugin.section_contents.show()
			plugin.section_slab.show()

			self.plugins_still_searching -= 1

		self.consider_showing_no_results_text()

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def plugin_handle_search_error(self, plugin, text):
		"""
		Handler for when a plugin returns an error
		"""

		plugin.is_running = False
		self.plugin_write_to_log(plugin, text, is_error = True)

		# must be outside the lock!
		self.plugin_handle_search_result(plugin, [], '')


	def plugin_handle_search_result(self, plugin, results, original_query):
		"""
		Handler for when a plugin returns some search results
		"""

		plugin.section_slab.hide() # for added performance

		plugin.is_running = False
		self.plugins_still_searching -= 1

		if plugin.hide_from_sidebar and len(self.current_query) < self.settings['min search string length']:

			# Handle the case where user presses backspace *very* quickly, and the
			# search starts when len(text) > min_search_string_length, but after
			# search_update_delay milliseconds this method is called while the
			# search entry now has len(text) < min_search_string_length

			# Anyways, it's hard to explain, but suffice to say it's a race
			# condition and we handle it here.

			results = []

		if original_query != self.current_query:
			results = []

		gtk.gdk.threads_enter()

		self.reset_plugin_section_contents(plugin)

		for result in results:

			icon_name = result['icon name']
			fallback_icon = plugin.fallback_icon or 'text-x-generic'

			if icon_name == 'inode/symlink':
				icon_name = None

			if icon_name is not None:
				icon_name = self.get_icon_name_from_theme(icon_name)

			elif result['type'] == 'xdg':
				icon_name = self.get_icon_name_from_path(result['command'])

			if icon_name is None:
				icon_name = fallback_icon

			button = self.add_app_button(result['name'], icon_name, plugin.section_contents, result['type'], result['command'], tooltip = result['tooltip'])
			button.app_info['context menu'] = result['context menu']


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


	def plugin_ask_for_reload_permission(self, plugin):
		"""
		Handler for when a plugin asks Cardapio whether it can reload its
		database
		"""

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)

		self.rebuild_timer = glib.timeout_add_seconds(self.settings['menu rebuild delay'], self.plugin_on_reload_permission_granted, plugin)


	def plugin_on_reload_permission_granted(self, plugin):
		"""
		Tell the plugin that it may rebuild its database now
		"""

		self.rebuild_timer = None
		plugin.on_reload_permission_granted()

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def cancel_all_plugins(self):
		"""
		Tell all plugins to stop a possibly-time-consuming search
		"""

		self.plugins_still_searching = 0

		for plugin in self.active_plugin_instances:

			if not plugin.is_running: continue

			try:
				plugin.cancel()

			except Exception, exception:
				self.plugin_write_to_log(plugin, 'Plugin failed to cancel query', is_error = True)
				logging.error(exception)


	def is_search_entry_empty(self):
		"""
		Returns True if the search entry is empty.
		"""

		return (len(self.search_entry.get_text().strip()) == 0)


	def on_search_entry_activate(self, widget):
		"""
		Handler for when the user presses Enter on the search entry
		"""

		if self.is_search_entry_empty():
			self.hide_all_transitory_sections()
			return

		first_app_widget = self.get_first_visible_app()
		if first_app_widget is not None:
			first_app_widget.emit('clicked')

		if not self.settings['keep search results']:
			self.clear_search_entry()
			self.untoggle_and_show_all_sections()


	def on_search_entry_key_pressed(self, widget, event):
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

			self.cancel_all_plugins()

			text = self.search_entry.get_text()
			slash_pos = text.rfind('/')

			if self.subfolder_stack and slash_pos != -1:
				if text[-1] == '/': slash_pos = text[:-1].rfind('/')
				text = text[:slash_pos+1]
				self.search_entry.set_text(text)
				self.search_entry.set_position(-1)

			elif not self.is_search_entry_empty():
				self.clear_search_entry()

			elif self.selected_section is not None:
				self.untoggle_and_show_all_sections()

			elif self.in_system_menu_mode:
				self.switch_modes(show_system_menus = False, toggle_mode_button = True)

			else:
				self.hide()

		else: return False
		return True


	def get_first_visible_app(self):
		"""
		Returns the first app in the right pane, if any.
		"""

		for slab in self.application_pane.get_children():
			if not slab.get_visible(): continue

			# NOTE: the following line depends on the UI file. If the file is
			# changed, this may raise an exception:

			for child in slab.get_children()[0].get_children()[0].get_children():
				if not child.get_visible(): continue
				if type(child) != gtk.Button: continue

				return child

		return None


	def get_selected_app(self):
		"""
		Returns the button for the selected app (that is, the one that has
		keyboard focus) if any.
		"""

		widget = self.previously_focused_widget

		if (type(widget) is gtk.Button and 'app_info' in dir(widget)):
			return widget

		return None


	def reposition_window(self, is_message_window = False, show_near_mouse = False):
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

		if show_near_mouse or self.panel_applet is None:

			if show_near_mouse:
				mouse_x, mouse_y, dummy = root_window.get_pointer()
				if mouse_x + window_width  > screen_x + screen_width : mouse_x = mouse_x - window_width
				if mouse_y + window_height > screen_y + screen_height: mouse_y = mouse_y - window_height
				if mouse_x + window_width  > screen_x + screen_width : mouse_x = screen_x + screen_width  - window_width
				if mouse_y + window_height > screen_y + screen_height: mouse_y = screen_y + screen_height - window_height
				if mouse_x < screen_x: mouse_x = screen_x
				if mouse_y < screen_y: mouse_y = screen_y
				window_x = mouse_x
				window_y = mouse_y

			else:
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

		if self.settings['splitter position'] > 0:
			self.get_object('MainSplitter').set_position(self.settings['splitter position'])


	def save_dimensions(self, *dummy):
		"""
		Save Cardapio's size into the user preferences
		"""

		self.settings['window size'] = self.window.get_size()
		self.settings['splitter position'] = self.get_object('MainSplitter').get_position()


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


	def show(self, *dummy, **kwargs):
		"""
		Show the Cardapio window
		"""

		if 'show_near_mouse' in kwargs:
			show_near_mouse = kwargs['show_near_mouse']
		else:
			show_near_mouse = False

		self.auto_toggle_panel_button(True)

		self.restore_dimensions()
		self.reposition_window(show_near_mouse = show_near_mouse)
		self.show_window_on_top(self.window)

		self.window.set_focus(self.search_entry)
 		self.scroll_to_top()

		self.visible = True
		self.last_visibility_toggle = time()

		self.opened_last_app_in_background = False

		if self.rebuild_timer is not None:
			# build the UI *after* showing the window, so the user gets the
			# satisfaction of seeing the window pop up, even if it's incomplete...
			self.rebuild_ui(show_message = True)

		if not self.settings['keep search results']:
			self.switch_modes(show_system_menus = False, toggle_mode_button = True)


	def hide(self, *dummy):
		"""
		Hide the Cardapio window
		"""

		self.auto_toggle_panel_button(False)

		self.visible = False
		self.last_visibility_toggle = time()

		self.window.hide()

		if not self.settings['keep search results']:
			self.clear_search_entry()
			self.untoggle_and_show_all_sections()

		self.cancel_all_plugins()

		return False # used for when hide() is called from a timer


	@dbus.service.method(dbus_interface = bus_name_str, in_signature = 'b', out_signature = None)
	def show_hide(self, show_near_mouse = False):
		"""
		Toggle Show/Hide the Cardapio window. This function is dbus-accessible.
		"""

		if time() - self.last_visibility_toggle < Cardapio.min_visibility_toggle_interval:
			return

		show_near_mouse = bool(show_near_mouse)

		if self.visible: self.hide()
		else: self.show(show_near_mouse = show_near_mouse)

		return True


	def hide_if_mouse_away(self):
		"""
		Hide the window if the cursor is *not* on top of it
		"""

		root_window = gtk.gdk.get_default_root_window()
		mouse_x, mouse_y, dummy = root_window.get_pointer()

		dummy, dummy, window_width, window_height = self.window.get_allocation()
		window_x, window_y = self.window.get_position()

		cursor_in_window_x = (window_x <= mouse_x <= window_x + window_width)
		cursor_in_window_y = (window_y <= mouse_y <= window_y + window_height)

		if self.panel_button:

			panel = self.panel_button.get_toplevel().window
			panel_x, panel_y = panel.get_origin()
			applet_x, applet_y, applet_width, applet_height = self.panel_button.get_allocation()
			applet_x += panel_x
			applet_y += panel_y
			cursor_in_applet_x = (applet_x <= mouse_x <= applet_x + applet_width)
			cursor_in_applet_y = (applet_y <= mouse_y <= applet_y + applet_height)

		else:
			cursor_in_applet_x = cursor_in_applet_y = True

		if (cursor_in_window_x and cursor_in_window_y) or (cursor_in_applet_x and cursor_in_applet_y):
			return

		self.hide()


	def show_window_on_top(self, window):
		"""
		Place the Cardapio window on top of all others
		"""

		window.stick()
		window.show_now()

		# for compiz, this must take place twice!!
		window.present_with_time(int(time()))
		window.present_with_time(int(time()))

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


	def on_panel_button_toggled(self, widget, event, ignore_main_button):
		"""
		Show/Hide cardapio when the panel applet is clicked
		"""

		if event.type == gtk.gdk.BUTTON_PRESS:

			if event.button == 1:

				if not ignore_main_button:
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

		if bg_type == gnomeapplet.COLOR_BACKGROUND:
			self.panel_button.parent.modify_bg(gtk.STATE_NORMAL, color)

		elif bg_type == gnomeapplet.PIXMAP_BACKGROUND:
			style = self.panel_button.parent.get_style()
			style.bg_pixmap[gtk.STATE_NORMAL] = pixmap
			self.panel_button.parent.set_style(style)

		#elif bg_type == gnomeapplet.NO_BACKGROUND: pass


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

		for node in self.sys_tree.root.contents:
			if isinstance(node, gmenu.Directory):
				self.add_slab(node.name, node.icon, node.get_comment(), node = node, system_menu = True)

		self.system_category_pane.hide()

		section_slab, section_contents, dummy = self.add_slab(_('Uncategorized'), 'applications-other', tooltip = _('Other configuration tools'), hide = False, system_menu = True)
		self.add_tree_to_app_list(self.sys_tree.root, section_contents, self.sys_list, recursive = False)

		self.add_tree_to_app_list(self.sys_tree.root, self.system_section_contents, self.app_list)


	def build_uncategorized_list(self):
		"""
		Populate the Uncategorized section
		"""

		self.add_tree_to_app_list(self.app_tree.root, self.uncategorized_section_contents, self.app_list, recursive = False)


	def build_places_list(self):
		"""
		Populate the places list
		"""

		self.build_bookmarked_places_list(self.places_section_contents)
		self.build_system_places_list(self.places_section_contents)


	def build_system_places_list(self, section_contents):
		"""
		Populate the "system places", which include Computer, the list of
		connected drives, and so on.
		"""

		if self.volume_monitor is None:
			volume_monitor_already_existed = False
			self.volume_monitor = gio.volume_monitor_get() # keep a reference to avoid getting it garbage-collected
		else:
			volume_monitor_already_existed = True

		self.volumes = {}

		for mount in self.volume_monitor.get_mounts():

			volume = mount.get_volume()
			if volume is None: continue

			name = volume.get_name()
			icon_name = self.get_icon_name_from_gio_icon(volume.get_icon())

			try    : command = str(volume.get_mount().get_root().get_uri())
			except : command = ''

			self.add_app_button(name, icon_name, section_contents, 'xdg', command, tooltip = command, app_list = self.app_list)
			self.volumes[command] = volume

		self.add_app_button(_('Network'), 'network', section_contents, 'xdg', 'network://', tooltip = _('Browse the contents of the network'), app_list = self.app_list)
		self.add_app_button(_('Trash'), 'user-trash', section_contents, 'xdg', 'trash:///', tooltip = _('Open the trash'), app_list = self.app_list)

		if not volume_monitor_already_existed:
			self.mount_added_handler   = self.volume_monitor.connect('mount-added', self.on_volume_monitor_changed, self.places_section_contents)
			self.mount_removed_handler = self.volume_monitor.connect('mount-removed', self.on_volume_monitor_changed, self.places_section_contents)


	def build_bookmarked_places_list(self, section_contents):
		"""
		Populate the "bookmarked places", which include Home and your personal bookmarks.
		"""

		self.add_app_button(_('Home'), 'user-home', section_contents, 'xdg', self.home_folder_path, tooltip = _('Open your personal folder'), app_list = self.app_list)

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
				path_type, dummy = urllib2.splittype(path)

				gio_path_obj = gio.File(path)
				if not gio_path_obj.query_exists() and path_type not in Cardapio.REMOTE_PROTOCOLS: continue

				self.add_place(name, path, 'folder')

		bookmark_file.close()

		if self.bookmark_monitor is None:
			self.bookmark_monitor = gio.File(bookmark_file_path).monitor_file() # keep a reference to avoid getting it garbage-collected
			self.bookmarks_changed_handler = self.bookmark_monitor.connect('changed', self.on_bookmark_monitor_changed, self.places_section_contents)


	def on_bookmark_monitor_changed(self, monitor, file, other_file, event, section_contents):
		"""
		Handler for when the user adds/removes a bookmarked folder using
		Nautilus or some other program
		"""

		if event == gio.FILE_MONITOR_EVENT_CHANGES_DONE_HINT:
			self.clear_pane(section_contents)
			self.build_places_list()


	def on_volume_monitor_changed(self, monitor, drive, section_contents):
		"""
		Handler for when volumes are mounted or ejected
		"""

		self.clear_pane(section_contents)
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

		# TODO: name remote folders like nautilus does (i.e. '/home on ftp.myserver.net')
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

		icon_name = self.get_icon_name_from_path(folder_path)
		if icon_name is None: icon_name = folder_icon
		self.add_app_button(folder_name, icon_name, self.places_section_contents, 'xdg', folder_path, tooltip = folder_path, app_list = self.app_list)


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

			# adding a new property that was not in the old config files...
			if 'context menu' not in app:
				app['context menu'] = None

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
				button = self.add_button(app['name'], app['icon name'], self.sidepane, tooltip = app['tooltip'], button_type = Cardapio.SIDEPANE_BUTTON)
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
			button = self.add_button(item[0], item[2], item[4], tooltip = item[1], button_type = Cardapio.SESSION_BUTTON)
			button.app_info = app_info
			button.connect('clicked', self.on_app_button_clicked)


	def build_applications_list(self):
		"""
		Populate the Applications list by reading the Gnome menus
		"""

		for node in self.app_tree.root.contents:
			if isinstance(node, gmenu.Directory):
				self.add_slab(node.name, node.icon, node.get_comment(), node = node, hide = False)


	def add_slab(self, title_str, icon_name = None, tooltip = '', hide = False, node = None, system_menu = False):
		"""
		Add to the app pane a new section slab (i.e. a container holding a title
		label and a hbox to be filled with apps). This also adds the section
		name to the left pane, under the View label.
		"""

		if system_menu:
			category_pane = self.system_category_pane
			app_list = self.sys_list
		else:
			category_pane = self.category_pane
			app_list = self.app_list

		# add category to category pane
		sidebar_button = self.add_button(title_str, icon_name, category_pane, tooltip = tooltip, button_type = Cardapio.CATEGORY_BUTTON)

		# add category to application pane
		section_slab, section_contents, label = self.add_application_section(title_str)

		if node is not None:
			# add all apps in this category to application pane
			self.add_tree_to_app_list(node, section_contents, app_list)

		sidebar_button.connect('clicked', self.on_sidebar_button_clicked, section_slab)

		if hide:
			sidebar_button.hide()
			section_slab.hide()
			self.section_list[section_slab] = {
					'has entries': False,
					'category': sidebar_button,
					'contents': section_contents,
					'name': title_str,
					'is system section': system_menu,
					}

		else:
			self.section_list[section_slab] = {
					'has entries': True,
					'category': sidebar_button,
					'contents': section_contents,
					'name': title_str,
					'is system section': system_menu,
					}

		return section_slab, section_contents, label


	def add_places_slab(self):
		"""
		Add the Places slab to the app pane
		"""

		section_slab, section_contents, dummy = self.add_slab(_('Places'), 'folder', tooltip = _('Access documents and folders'), hide = False)
		self.places_section_slab = section_slab
		self.places_section_contents = section_contents


	def add_subfolders_slab(self):
		"""
		Add the Folder Contents slab to the app pane
		"""

		section_slab, section_contents, label = self.add_slab(_('Folder Contents'), 'system-file-manager', tooltip = _('Look inside folders'), hide = True)
		self.subfolders_section_slab = section_slab
		self.subfolders_section_contents = section_contents
		self.subfolders_label = label


	def add_pinneditems_slab(self):
		"""
		Add the Pinned Items slab to the app pane
		"""

		section_slab, section_contents, dummy = self.add_slab(_('Pinned items'), 'emblem-favorite', tooltip = _('Your favorite items'), hide = False)
		self.favorites_section_slab = section_slab
		self.favorites_section_contents = section_contents


	def add_sidepane_slab(self):
		"""
		Add the Side Pane slab to the app pane
		"""

		section_slab, section_contents, dummy = self.add_slab(_('Side Pane'), 'emblem-favorite', tooltip = _('Items pinned to the side pane'), hide = True)
		self.sidepane_section_slab = section_slab
		self.sidepane_section_contents = section_contents


	def add_uncategorized_slab(self):
		"""
		Add the Uncategorized slab to the app pane
		"""

		section_slab, section_contents, dummy = self.add_slab(_('Uncategorized'), 'applications-other', tooltip = _('Items that are not under any menu category'), hide = True)
		self.uncategorized_section_slab = section_slab
		self.uncategorized_section_contents = section_contents


	def add_session_slab(self):
		"""
		Add the Session slab to the app pane
		"""

		section_slab, section_contents, dummy = self.add_slab(_('Session'), 'session-properties', hide = True)
		self.session_section_slab = section_slab
		self.session_section_contents = section_contents


	def add_system_slab(self):
		"""
		Add the System slab to the app pane
		"""

		section_slab, section_contents, dummy = self.add_slab(_('System'), 'applications-system', hide = True)
		self.system_section_slab = section_slab
		self.system_section_contents = section_contents


	def add_plugin_slab(self, basename):
		"""
		Add the slab for a plugin (as identified by the basename)
		"""

		if basename not in self.plugin_database:
			self.settings['active plugins'].remove(basename)
			return

		plugin = self.plugin_database[basename]['instance']
		if plugin is None: return

		section_slab, section_contents, dummy = self.add_slab(plugin.category_name, plugin.category_icon, plugin.category_tooltip, hide = plugin.hide_from_sidebar)
		plugin.section_slab = section_slab
		plugin.section_contents = plugin.section_slab.get_children()[0].get_children()[0]


	def add_all_reorderable_slabs(self):
		"""
		Add all the reorderable slabs to the app pane
		"""

		self.add_sidepane_slab()

		for basename in self.settings['active plugins']:

			if basename == 'applications':
				self.build_applications_list()
				self.add_uncategorized_slab()
				self.add_session_slab()
				self.add_system_slab()

			elif basename == 'places':
				self.add_places_slab()

			elif basename == 'pinned':
				self.add_pinneditems_slab()

			else:
				self.add_plugin_slab(basename)


	def clear_pane(self, container):
		"""
		Remove all children from a GTK container
		"""

		# this is necessary when clearing section contents, but does nothing
		# when clearing other containers:
		self.app_list = [app for app in self.app_list if app['section'] != container.parent.parent]
		self.sys_list = [app for app in self.sys_list if app['section'] != container.parent.parent]

		for	child in container.get_children():
			container.remove(child)


	def clear_search_entry(self):
		"""
		Clears the search entry
		"""

		self.search_entry.set_text('')
		self.subfolder_stack = []


	def add_app_button(self, button_str, icon_name, parent_widget, command_type, command, tooltip = '', app_list = None):
		"""
		Adds a new button to the app pane
		"""

		button = self.add_button(button_str, icon_name, parent_widget, tooltip, button_type = Cardapio.APP_BUTTON)

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

		if command_type != 'callback' and command_type != 'raw':

			if command_type == 'app':
				button.drag_source_set(
						gtk.gdk.BUTTON1_MASK,
						[('text/uri-list', 0, 0)],
						gtk.gdk.ACTION_COPY)
			else:
				button.drag_source_set(
						gtk.gdk.BUTTON1_MASK,
						[('text/uri-list', 0, 0)],
						gtk.gdk.ACTION_LINK)

			button.connect('drag-begin', self.on_app_button_drag_begin)
			button.connect('drag-data-get', self.on_app_button_data_get)
			# TODO: drag and drop to reorganize pinned items

		# save some metadata for easy access
		button.app_info = {
			'name'         : self.unescape(button_str),
			'tooltip'      : tooltip,
			'icon name'    : icon_name,
			'command'      : command,
			'type'         : command_type,
			'context menu' : None,
		}

		return button


	def add_button(self, button_str, icon_name, parent_widget, tooltip = '', button_type = APP_BUTTON):
		"""
		Adds a button to a parent container
		"""

		if button_type != Cardapio.CATEGORY_BUTTON:
			button = gtk.Button()
		else:
			button = gtk.ToggleButton()

		button_str = self.unescape(button_str)

		label = gtk.Label(button_str)

		if button_type == Cardapio.APP_BUTTON:
			icon_size_pixels = self.icon_size_app
			label.modify_fg(gtk.STATE_NORMAL, self.style_app_button_fg)

			# TODO: figure out how to set max width so that it is the best for
			# the window and font sizes
			#layout = label.get_layout()
			#extents = layout.get_pixel_extents()
			#label.set_ellipsize(ELLIPSIZE_END)
			#label.set_max_width_chars(20)

		elif button_type == Cardapio.CATEGORY_BUTTON or button_type == Cardapio.SIDEPANE_BUTTON:
			icon_size_pixels = self.icon_size_category

		else:
			icon_size_pixels = self.icon_size_app

		icon_pixbuf = self.get_icon_pixbuf(icon_name, icon_size_pixels)
		icon = gtk.image_new_from_pixbuf(icon_pixbuf)

		hbox = gtk.HBox()
		hbox.add(icon)
		hbox.add(label)
		hbox.set_spacing(5)
		hbox.set_homogeneous(False)

		align = gtk.Alignment(0, 0.5)
		align.add(hbox)

		if tooltip:
			tooltip = self.unescape(tooltip)
			button.set_tooltip_text(tooltip)

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

		section_contents = gtk.VBox(homogeneous = True)

		section_margin = gtk.Alignment(0.5, 0.5, 1.0, 1.0)
		section_margin.add(section_contents)
		section_margin.set_padding(0, 0, 4, 0)

		label = gtk.Label()
		label.set_use_markup(True)
		label.modify_fg(gtk.STATE_NORMAL, self.style_app_button_fg)
		label.set_padding(0, 4)
		label.set_attributes(self.section_label_attributes)

		if section_title is not None:
			label.set_text(section_title)

		section_slab = gtk.Frame()
		section_slab.set_label_widget(label)
		section_slab.set_shadow_type(gtk.SHADOW_NONE)
		section_slab.add(section_margin)

		section_slab.show_all()

		self.application_pane.pack_start(section_slab, expand = False, fill = False)

		return section_slab, section_contents, label


	def get_icon_pixbuf(self, icon_value, icon_size, fallback_icon = 'application-x-executable'):
		"""
		Returns a GTK Image from a given icon name and size. The icon name can be
		either a path or a named icon from the GTK theme.
		"""

		# TODO: speed this up as much as possible!

		if not icon_value:
			icon_value = fallback_icon

		icon_pixbuf = None
		icon_name = icon_value

		if os.path.isabs(icon_value):
			if os.path.isfile(icon_value):
				try: icon_pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(icon_value, icon_size, icon_size)
				except: pass
			icon_name = os.path.basename(icon_value)

		if self.icon_extension_types.match(icon_name) is not None:
			icon_name = icon_name[:-4]

		if icon_pixbuf is None:
			cleaned_icon_name = self.get_icon_name_from_theme(icon_name)
			if cleaned_icon_name is not None:
				try: icon_pixbuf = self.icon_theme.load_icon(cleaned_icon_name, icon_size, gtk.ICON_LOOKUP_FORCE_SIZE)
				except: pass

		if icon_pixbuf is None:
			for dir_ in BaseDirectory.xdg_data_dirs:
				for subdir in ('pixmaps', 'icons'):
					path = os.path.join(dir_, subdir, icon_value)
					if os.path.isfile(path):
						try: icon_pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(path, icon_size, icon_size)
						except: pass

		if icon_pixbuf is None:
			icon_pixbuf = self.icon_theme.load_icon(fallback_icon, icon_size, gtk.ICON_LOOKUP_FORCE_SIZE)

		return icon_pixbuf


	def get_icon_name_from_theme(self, icon_name):
		"""
		Find out if this icon exists in the theme (such as 'gtk-open'), or if
		it's a mimetype (such as audio/mpeg, which has an icon audio-mpeg), or
		if it has a generic mime icon (such as audio-x-generic)
		"""

		# replace slashed with dashes for mimetype icons
		cleaned_icon_name = icon_name.replace('/', '-')

		if self.icon_theme.has_icon(cleaned_icon_name):
			return cleaned_icon_name

		# try generic mimetype
		gen_type = cleaned_icon_name.split('-')[0]
		cleaned_icon_name = gen_type + '-x-generic'
		if self.icon_theme.has_icon(cleaned_icon_name):
			return cleaned_icon_name

		return None


	def get_icon_name_from_path(self, path):
		"""
		Gets the icon name for a given path using GIO
		"""

		info = None

		try:
			file_ = gio.File(path)
			info = file_.query_info('standard::icon')

		except Exception, exception:
			logging.warn('Could not get icon for %s' % path)
			logging.warn(exception)
			return None

		if info is not None:
			icons = info.get_icon().get_property('names')
			for icon_name in icons:
				if self.icon_theme.has_icon(icon_name):
					return icon_name

		return None


	def get_icon_name_from_gio_icon(self, gio_icon, icon_size = None):
		"""
		Gets the icon name from a GIO icon object
		"""

		if icon_size == None: icon_size = self.icon_size_app

		try:
			names = self.icon_theme.lookup_by_gicon(gio_icon, icon_size, 0)
			if names: return names.get_filename()

		except: pass

		try:
			for name in gio_icon.get_names():
				if self.icon_theme.has_icon(name): return name

		except: pass

		return None

	def add_tree_to_app_list(self, tree, parent_widget, app_list, recursive = True):
		"""
		Adds all the apps in a subtree of Gnome's menu as buttons in a given
		parent widget
		"""

		for node in tree.contents:

			if isinstance(node, gmenu.Entry):

				self.add_app_button(node.name, node.icon, parent_widget, 'app', node.desktop_file_path, tooltip = node.get_comment(), app_list = app_list)

			elif isinstance(node, gmenu.Directory) and recursive:

				self.add_tree_to_app_list(node, parent_widget, app_list)


	def read_gtk_theme_info(self):
		"""
		Reads colors and other info from the GTK theme so that the app better
		adapt to any custom theme
		"""

		dummy_window = gtk.Window()
		dummy_window.set_name('ApplicationPane')
		dummy_window.realize()
		app_style = dummy_window.get_style()
		self.style_app_button_bg = app_style.base[gtk.STATE_NORMAL]
		self.style_app_button_fg = app_style.text[gtk.STATE_NORMAL]
		self.get_object('ScrolledViewport').modify_bg(gtk.STATE_NORMAL, self.style_app_button_bg)

		scrollbar = gtk.VScrollbar()
		self.scrollbar_width = scrollbar.style_get_property('slider-width')


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
		self.get_object('SideappSubdivider').queue_resize() # required! or sidepane will obscure the mode switcher button


	def on_remove_from_side_pane_clicked(self, widget):
		"""
		Handle the "remove from sidepane" action
		"""

		self.remove_section_from_app_list(self.sidepane_section_slab)
		self.clear_pane(self.sidepane_section_contents)
 		self.clear_pane(self.sidepane)
		self.settings['side pane items'].remove(self.clicked_app)
		self.build_favorites_list(self.sidepane_section_slab, 'side pane items')
		self.get_object('SideappSubdivider').queue_resize() # required! or an extra space will show up where but button used to be


	def on_open_parent_folder_pressed(self, widget):
		"""
		Handle the "open parent folder" action
		"""

		parent_folder, dummy = os.path.split(self.clicked_app['command'])
		self.launch_xdg(parent_folder)


	def on_launch_in_background_pressed(self, widget):
		"""
		Handle the "launch in background" action
		"""

		self.launch_button_command(self.clicked_app, hide = False)


	def on_peek_inside_pressed(self, widget):
		"""
		Handle the "peek inside folder" action
		"""

		dummy, path = urllib2.splittype(self.clicked_app['command'])
		if os.path.isfile(path): path, dummy = os.path.split(path)
 		self.create_subfolder_stack(path)
		self.search_entry.set_text(self.subfolder_stack[-1][1] + '/')


	def on_eject_pressed(self, widget):
		"""
		Handle the "eject" action
		"""

		volume = self.volumes[self.clicked_app['command']]
		volume.eject(return_true)


	def on_app_button_button_pressed(self, widget, event):
		"""
		Show context menu for app buttons
		"""

		if event.type != gtk.gdk.BUTTON_PRESS: return

		if  event.button == 2:

			self.launch_button_command(widget.app_info, hide = False)

		elif event.button == 3:

			self.setup_context_menu(widget)
			self.block_focus_out_event()
			self.app_context_menu.popup(None, None, None, event.button, event.time)


	def setup_context_menu(self, widget):
		"""
		Show or hide different context menu options depending on the widget
		"""

		self.clicked_app = widget.app_info

		self.open_folder_menuitem.hide()
		self.peek_inside_menuitem.hide()
		self.eject_menuitem.hide()

		if widget.app_info['type'] == 'callback':
			self.pin_menuitem.hide()
			self.unpin_menuitem.hide()
			self.add_side_pane_menuitem.hide()
			self.remove_side_pane_menuitem.hide()
			self.app_menu_separator.hide()
			self.plugin_setup_context_menu()
			return

		already_pinned = False
		already_on_side_pane = False
		self.app_menu_separator.show()

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


		# figure out whether to show the 'open parent folder' menuitem
		split_command = urllib2.splittype(widget.app_info['command'])

		if widget.app_info['type'] == 'xdg' or len(split_command) == 2:

			path_type, canonical_path = split_command
			dummy, extension = os.path.splitext(canonical_path)

			# don't show it for network://, trash://, or .desktop files
			if path_type not in ('computer', 'network', 'trash') and extension != '.desktop':

				# only show if path that exists
				if os.path.exists(self.unescape(canonical_path)):
					self.open_folder_menuitem.show()
					self.peek_inside_menuitem.show()

		# figure out whether to show the 'eject' menuitem
		if widget.app_info['command'] in self.volumes:
			self.eject_menuitem.show()

		self.plugin_setup_context_menu()


	def plugin_setup_context_menu(self):
		"""
		Sets up context menu items as requested by individual plugins
		"""

		self.plugin_clear_context_menu()
		if 'context menu' not in self.clicked_app: return
		if self.clicked_app['context menu'] is None: return
		self.plugin_fill_context_menu()


	def plugin_clear_context_menu(self):
		"""
		Remove all plugin-dependent actions from the context menu
		"""

		for menu_item in self.app_context_menu:
			if menu_item.name is not None and menu_item.name.startswith('PluginAction'):
				self.app_context_menu.remove(menu_item)


	def plugin_fill_context_menu(self):
		"""
		Add plugin-related actions to the context menu
		"""

		i = 0

		for item_info in self.clicked_app['context menu']:

			menu_item = gtk.ImageMenuItem(item_info['name'], True)
			menu_item.set_tooltip_text(item_info['tooltip'])
			menu_item.set_name('PluginAction' + str(i))
			i += 1

			if item_info['icon name'] is not None:
				icon_pixbuf = self.get_icon_pixbuf(item_info['icon name'], self.icon_size_menu)
				icon = gtk.image_new_from_pixbuf(icon_pixbuf)
				menu_item.set_image(icon)

			menu_item.app_info = item_info
			menu_item.connect('activate', self.on_app_button_clicked)

			menu_item.show_all()
			self.app_context_menu.append(menu_item)


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


	def on_app_button_drag_begin(self, button, drag_context):
		"""
		Set up drag action (not much goes on here...)
		"""

		icon_pixbuf = self.get_icon_pixbuf(button.app_info['icon name'], self.icon_size_app)
		button.drag_source_set_icon_pixbuf(icon_pixbuf)


	def on_app_button_data_get(self, button, drag_context, selection_data, info, time):
		"""
		Prepare the data that will be sent to the other app when the drag-and-drop
		operation is done
		"""

		command = button.app_info['command']
		command_type = button.app_info['type']

		if command_type == 'app':
			command = 'file://' + command

		elif command_type == 'xdg':

			path_type, dummy = urllib2.splittype(command)
			if path_type is None: command = 'file://' + command

			# TODO: figure out how to handle drag-and-drop for 'computer://' and
			# 'trash://' (it seems that nautilus has the same problems...)

		# TODO: handle command_type == 'raw' by creating a new desktop file and link?
		selection_data.set_uris([command])


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
			text = self.current_query
			if hide: self.hide()
			command(text)


	def launch_desktop(self, command, hide = True):
		"""
		Launch applications represented by .desktop files
		"""

		if os.path.exists(command):

			path = DesktopEntry.DesktopEntry(command).getExec()

			# Strip parts of the path that contain %<a-Z>

			path_parts = path.split()

			for i in xrange(len(path_parts)):
				if path_parts[i][0] == '%':
					path_parts[i] = ''

			path = ' '.join(path_parts)

			return self.launch_raw(path, hide)

		else:
			logging.warn('Tried launching an app that does not exist: %s' % desktop_path)


	def launch_xdg(self, path, hide = True):
		"""
		Open a url, file or folder
		"""

		path = self.escape_quotes(self.unescape(path))
		path_type, dummy = urllib2.splittype(path)

		# if the file is executable, ask what to do
		if os.path.isfile(path) and os.access(path, os.X_OK):

			dummy, extension = os.path.splitext(path)

			# treat '.desktop' files differently
			if extension == '.desktop':
				self.launch_desktop(path, hide)
				return

			else:
				# show "Run in Terminal", "Display", "Cancel", "Run"
				response = self.show_executable_file_dialog(path)

				# if "Run in Terminal"
				if response == 1:
					return self.launch_raw_in_terminal(path, hide)

				# if "Display"
				elif response == 2:
					pass

				# if "Run"
				elif response == 3:
					return self.launch_raw(path, hide)

				# if "Cancel"
				else:
					return

		elif path_type in Cardapio.REMOTE_PROTOCOLS:
			special_handler = self.settings['handler for %s paths' % path_type]
			return self.launch_raw(special_handler % path, hide)

		return self.launch_raw("xdg-open '%s'" % path, hide)


	def launch_raw(self, path, hide = True):
		"""
		Run a command as a subprocess
		"""

		try:
			if self.panel_applet:
				# allow launched apps to use Ubuntu's AppMenu
				os.environ['UBUNTU_MENUPROXY'] = 'libappmenu.so'

			subprocess.Popen(path, shell = True, cwd = self.home_folder_path)

		except Exception, exception:
			logging.error('Could not launch %s' % path)
			logging.error(exception)
			return False

		if hide: self.hide()

		return True


	def launch_raw_in_terminal(self, path, hide = True):
		"""
		Run a command inside Gnome's default terminal
		"""

		try:
			gnome_execute_terminal_shell(self.home_folder_path, path)

		except Exception, exception:
			logging.error('Could not launch %s' % path)
			logging.error(exception)
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


	def untoggle_and_show_all_sections(self):
		"""
		Show all sections that currently have search results, and untoggle all
		category buttons
		"""

		self.no_results_to_show = True

		for sec in self.section_list:
			if self.section_list[sec]['has entries'] and self.section_list[sec]['is system section'] == self.in_system_menu_mode:
				sec.show()
				self.no_results_to_show = False
			else:
				sec.hide()

		if not self.no_results_to_show:
			self.hide_no_results_text()

		if self.selected_section is not None:
			widget = self.section_list[self.selected_section]['category']
			self.set_sidebar_button_active(widget, False)

		self.selected_section = None

		if self.in_system_menu_mode:
			widget = self.all_system_sections_sidebar_button
		else:
			widget = self.all_sections_sidebar_button

		self.set_sidebar_button_active(widget, True)

		if self.is_search_entry_empty():
			widget.set_sensitive(False)


	def toggle_and_show_section(self, section_slab):
		"""
		Show a given section, make sure its button is toggled, and that
		no other buttons are toggled
		"""

		for sec in self.section_list:
			sec.hide()

		if self.selected_section is not None:
			widget = self.section_list[self.selected_section]['category']
			self.set_sidebar_button_active(widget, False)

		elif self.in_system_menu_mode and self.all_system_sections_sidebar_button.get_active():
			widget = self.all_system_sections_sidebar_button
			self.set_sidebar_button_active(widget, False)

		elif self.all_sections_sidebar_button.get_active():
			widget = self.all_sections_sidebar_button
			self.set_sidebar_button_active(widget, False)

		self.all_sections_sidebar_button.set_sensitive(True)
		self.all_system_sections_sidebar_button.set_sensitive(True)
		self.selected_section = section_slab

		self.consider_showing_no_results_text()
 		self.scroll_to_top()


	def show_no_results_text(self, text = None):
		"""
		Show the "No results to show" text
		"""

		if text is None: text = self.no_results_text

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

			if self.plugins_still_searching > 0:
				return

			if self.no_results_to_show:
				self.show_no_results_text()

			return

		if self.section_list[self.selected_section]['has entries']:
			self.selected_section.show()
			self.hide_no_results_text()

		else:
			self.selected_section.hide()
			self.show_no_results_text(self.no_results_in_category_text % {'category_name': self.section_list[self.selected_section]['name']})


	def hide_all_transitory_sections(self, fully_hide = False):
		"""
		Hides all sections that should not appear in the sidebar when
		there is no text in the search entry
		"""

		self.hide_section(self.subfolders_section_slab, fully_hide)
		self.hide_section(self.session_section_slab, fully_hide)
		self.hide_section(self.system_section_slab, fully_hide)
		self.hide_section(self.sidepane_section_slab, fully_hide)
		self.hide_section(self.uncategorized_section_slab, fully_hide)

		self.hide_transitory_plugin_sections(fully_hide)


	def hide_section(self, section_slab, fully_hide = False):
		"""
		Hide a section slab
		"""

		if fully_hide:
			self.set_section_is_empty(section_slab)

		section_slab.hide()


	def fully_hide_all_sections(self):
		"""
		Hide all sections, including plugins and non-plugins
		"""

		for section_slab in self.section_list:
			self.set_section_is_empty(section_slab)
			section_slab.hide()


	def hide_transitory_plugin_sections(self, fully_hide = False):
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

	plugin_api_version = 1.39

	search_delay_type = 'local'

	default_keyword  = ''

	category_name    = ''
	category_icon    = ''
	category_tooltip = ''

	fallback_icon    = ''

	hide_from_sidebar = True

	def __init__(self, cardapio_proxy):
		"""
		REQUIRED

		This constructor gets called whenever a plugin is activated.
		(Typically once per session, unless the user is turning plugins on/off)

		The constructor *must* set the instance variable self.loaded to True of False.
		For example, the Tracker plugin sets self.loaded to False if Tracker is not
		installed in the system.

		The constructor is given a single parameter, which is an object used to
		communicate with Cardapio. This object has the following members:

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

		   - ask_for_reload_permission - a function that should be used whenever
			 the plugin wants to reload its database. Not all plugins have
			 internal databases, though, so this is not always applicable. This
			 is used, for example, with the software_center plugin. (see
 		     on_reload_permission_granted below for more info)

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


	def search(self, text, result_limit):
		"""
		REQUIRED

		This method gets called when a new text string is entered in the search
		field. It also takes an argument indicating the maximum number of
		results Cardapio's expecting. The plugin should always provide as many
		results as it can but their number cannot exceed the given limit!

		One of the following functions should be called from this method
		(of from a thread spawned by this method):

		   * if all goes well:
		   --> handle_search_result(plugin, results, original_query)

		   * if there is an error
		   --> handle_search_error(plugin, text)

		The arguments to these functions are:

		   * plugin          - this plugin instance (that is, it should always
		                       be "self", without quotes)
		   * text            - some text to be inserted in Cardapio's log.
		   * results         - an array of dict items as described below.
		   * original_query  - the search query that this corresponds to. The
		                       plugin should save the query received by the
							   search() method and pass it back to Cardapio.

		item = {
		  'name'         : _('Music'),
		  'tooltip'      : _('Show your Music folder'),
		  'icon name'    : 'text-x-generic',
		  'type'         : 'xdg',
		  'command'      : '~/Music',
		  'context menu' : None
		  }

		Where setting 'type' to 'xdg' means that 'command' should be opened
		using xdg-open (you should give it a try it in the terminal, first!).
		Meanwhile, setting 'type' to 'callback' means that 'command' is a
		function that should be called when the item is clicked. This function
		will receive as an argument the current search string.

		Note that you can set item['file name'] to None if you want Cardapio
		to guess the icon from the 'command'. This only works for 'xdg' commands,
		though.

		To change what is shown in the context menu for the search results, set
		the 'context menu' field to a list [] of dictionary items exactly like
		the ones above.
		"""
		pass


	def cancel(self):
		"""
		NOT REQUIRED

		This function should cancel the search operation. This is useful if the search is
		done in a separate thread (which it should, as much as possible)
		"""
		pass


	def on_reload_permission_granted(self):
		"""
		NOT REQUIRED

		Whenever a plugin wishes to rebuild some sort of internal database,
		if this takes more than a couple of milliseconds it is advisable to
		first ask Cardapio for permission. This is how this works:

		1) Plugin calls cardapio_proxy.ask_for_reload_permission(self)

		Cardapio then decides at what time it is best to give the plugin the
		reload permission. Usually this can take up to 10s, to allow several
		plugins to reload at the same time. Then, Cardapio shows the "Data has
		changed" window.

		2) Cardapio calls on_reload_permission_granted to tell the plugin that
		it can reload its database

		When done, the "Data has changed" window is hidden.
		"""
		pass


def return_true(*dummy): return True
def return_false(*dummy): return False

def applet_factory(applet, iid):

	button = gtk.ImageMenuItem()

	cardapio = Cardapio(hidden = True, panel_button = button, panel_applet = applet)

	button.set_tooltip_text(_('Access applications, folders, system settings, etc.'))
	button.set_always_show_image(True)
	button.set_name('CardapioApplet')

	menubar = gtk.MenuBar()
	menubar.set_name('CardapioAppletMenu')
	menubar.add(button)

	gtk.rc_parse_string('''
		style "cardapio-applet-menu-style"
		{
			xthickness = 0
			ythickness = 0
			GtkMenuBar::shadow-type      = GTK_SHADOW_NONE
			GtkMenuBar::internal-padding = 0
			GtkMenuBar::focus-padding    = 0
			GtkWidget::focus-padding     = 0
			GtkWidget::focus-line-width  = 0
			#bg[NORMAL] = "#ff0000"
			engine "murrine" {} # fix background color bug
		}

		style "cardapio-applet-style"
		{
			xthickness = 0
			ythickness = 0
			GtkWidget::focus-line-width = 0
			GtkWidget::focus-padding    = 0
		}

		widget "*CardapioAppletMenu" style:highest "cardapio-applet-menu-style"
		widget "*PanelApplet" style:highest "cardapio-applet-style"
		''')

	applet.add(menubar)

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


