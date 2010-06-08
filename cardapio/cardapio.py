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
# TODO: make applet extend in every direction
# TODO: handle left and right panel orientations (rotate menuitem), and change-orient signal

# After version 1.0:
# TODO: make a preferences window that exposes the options from .config/Cardapio/config.ini
# TODO: make "places" use custom icons
# TODO: fix Win+Space untoggle
# TODO: fix tabbing of first_app_widget
# TODO: alt-1, alt-2, ..., alt-9, alt-0 should activate categories
# TODO: add mount points to "places", allow ejecting from context menu
# TODO: multiple columns when window is wide enough (like gnome-control-center)
# TODO: slash "/" should navigate inside folders, Esc pops out
# TODO: search results have context menu with "Open with...", "Show parent folder", and so on.
# TODO: figure out if tracker can sort the results by relevancy
# TODO: make on_icon_theme_changed / on_gtk_settings_changed more lightweight by keeping all themeable widgets in an array
# TODO: add debug console window to cardapio, to facilitate debugging the applet
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
	menu_editing_apps = ('alacarte', 'gmenu-simple-editor')

	min_visibility_toggle_interval = 0.010 # seconds (this is a bit of a hack to fix some focus problems)

	bus_name_str = 'org.varal.Cardapio'
	bus_obj_str  = '/org/varal/Cardapio'

	plugin_api_version = 1.0


	def __init__(self, hidden = False, panel_applet = None, panel_button = None):

		self.read_config_file()

		self.user_home_folder = os.path.expanduser('~')

		self.panel_applet = panel_applet
		self.panel_button = panel_button
		self.auto_toggled_sidebar_button = False
		self.last_visibility_toggle = 0

		self.visible = False
		self.app_list = []
		self.section_list = {}
		self.selected_section = None
		self.no_results_to_show = False
		self.plugin_files = []
		self.active_plugins = []

		self.app_tree = gmenu.lookup_tree('applications.menu')
		self.sys_tree = gmenu.lookup_tree('settings.menu')

		# TODO: internationalize these
		self.exec_pattern = re.compile("^(.*?)\s+\%[a-zA-Z]$")
		self.sanitize_query_pattern = re.compile("[^a-zA-Z0-9]")

		self.setup_dbus()
		self.setup_plugins()
		self.setup_ui()

		self.app_tree.add_monitor(self.on_menu_data_changed)
		self.sys_tree.add_monitor(self.on_menu_data_changed)

		self.keybinding = self.settings['keybinding']
		keybinder.bind(self.keybinding, self.show_hide)

		if not hidden: self.show()


	def quit(self, *dummy):

		self.save_config_file()
		gtk.main_quit()


	def setup_dbus(self):

		DBusGMainLoop(set_as_default=True)
		self.bus = dbus.SessionBus()
		dbus.service.Object.__init__(self, self.bus, Cardapio.bus_obj_str)

	
	def setup_plugins(self):

		self.search_timer_local  = None
		self.search_timer_remote = None
		self.discover_plugins()
		self.activate_plugins()


	def activate_plugins(self):

		self.active_plugins = []

		package_root = ''
		if __package__ is not None:
			package_root = __package__ + '.'
		
		for active_plugin in self.settings['active plugins']:

			active_plugin_file = active_plugin + '.py'

			if active_plugin_file in self.plugin_files:

				package = '%splugins.%s' % (package_root, active_plugin)
				plugin_module = __import__(package, fromlist = 'CardapioPlugin', level = -1)
				plugin = plugin_module.CardapioPlugin(self.settings, self.handle_search_result, self.handle_search_error)
				if plugin.plugin_api_version != Cardapio.plugin_api_version: continue

				self.active_plugins.append(plugin)
				

	def discover_plugins(self):

		plugin_dir = os.path.join(os.path.dirname(__file__), 'plugins')

		for root, dir, files in os.walk(plugin_dir):
			for file_ in files:
				filename = os.path.join(root, file_)

				if len(file_) > 3 and file_[-3:] == '.py':
					self.plugin_files.append(file_)


	def on_logout_button_clicked(self, widget):

		self.do_session_action(shutdown = False)


	def on_shutdown_button_clicked(self, widget):

		self.do_session_action(shutdown = True)


	def do_session_action(self, shutdown):

		sm_proxy = self.bus.get_object('org.gnome.SessionManager', '/org/gnome/SessionManager')
		sm_if = dbus.Interface(sm_proxy, 'org.gnome.SessionManager')

		if shutdown : sm_if.Shutdown()
		else        : sm_if.Logout(0)

		self.hide()


	def on_lockscreen_button_clicked(self, widget):

		self.hide()

		try:
			screensaver_object = self.bus.get_object('org.gnome.ScreenSaver', '/org/gnome/ScreenSaver')
			dbus.Interface(screensaver_object, 'org.gnome.ScreenSaver').Lock()

		except dbus.DBusException, e:
			# NoReply exception may occur even while the screensaver did lock the screen
			if e.get_dbus_name() != 'org.freedesktop.DBus.Error.NoReply':
				pass


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

		try     : s = json.load(config_file)
		except  : pass
		finally : config_file.close()

		self.set_config_option(s, 'window size'                , None           ) # format: [px, px]
		self.set_config_option(s, 'show session buttons'       , False          ) # bool
		self.set_config_option(s, 'min search string length'   , 3              ) # characters
		self.set_config_option(s, 'menu rebuild delay'         , 30             ) # seconds
		self.set_config_option(s, 'search results limit'       , 5              ) # results
		self.set_config_option(s, 'local search update delay'  , 100            ) # msec
		self.set_config_option(s, 'remote search update delay' , 500            ) # msec
		self.set_config_option(s, 'keybinding'                 , '<Super>space' ) # the user should use gtk.accelerator_parse('<Super>space') to see if the string is correct!
		self.set_config_option(s, 'applet label'               , Cardapio.distro_name) # string
		self.set_config_option(s, 'active plugins'             , ['tracker', 'google']) # filenames

		# this is useful so that the user can edit the config file on first-run 
		# without need to quit cardapio first:
		self.save_config_file()


	def set_config_option(self, s, key, val):

		if key in s:
			self.settings[key] = s[key]
		else: 
			self.settings[key] = val


	def save_config_file(self):

		config_file = self.get_config_file('w')
		json.dump(self.settings, config_file, sort_keys = True, indent = 4)


	def setup_ui(self):

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
		self.application_pane   = self.get_object('ApplicationPane')
		self.category_pane      = self.get_object('CategoryPane')
		self.sideapp_pane       = self.get_object('SideappPane')
		self.search_entry       = self.get_object('SearchEntry')
		self.scrolled_window    = self.get_object('ScrolledWindow')
		self.scroll_adjustment  = self.scrolled_window.get_vadjustment()
		self.session_pane       = self.get_object('SessionPane')
		self.left_session_pane  = self.get_object('LeftSessionPane')
		self.right_session_pane = self.get_object('RightSessionPane')

		self.icon_theme = gtk.icon_theme_get_default()
		self.icon_theme.connect('changed', self.on_icon_theme_changed)
		self.icon_size_app = gtk.icon_size_lookup(gtk.ICON_SIZE_LARGE_TOOLBAR)[0]
		self.icon_size_category = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)[0]

		# make sure buttons have icons!
		self.gtk_settings = gtk.settings_get_default()
		self.gtk_settings.set_property('gtk-button-images', True)
		self.gtk_settings.connect('notify', self.on_gtk_settings_changed)

		self.window.set_keep_above(True)

		self.context_menu_xml = '''
			<popup name="button3">
				<menuitem name="Item 1" verb="Edit" label="%s" pixtype="stock" pixname="gtk-edit"/>
				<menuitem name="Item 2" verb="AboutCardapio" label="%s" pixtype="stock" pixname="gtk-about"/>
				<separator />
				<menuitem name="Item 3" verb="AboutGnome" label="%s" pixtype="stock" pixname="gtk-about"/>
				<menuitem name="Item 4" verb="AboutDistro" label="%s" pixtype="stock" pixname="gtk-about"/>
			</popup>
			''' % (
				_('_Edit Menus'), 
				_('_About Cardapio'), 
				_('_About Gnome'), 
				_('_About %(distro_name)s') % {'distro_name' : Cardapio.distro_name}
			)

		# NOTE: pixtype="filename" should be used for both
		# "gnome-logo-icon-transparent" and "distributor-logo", but it requires
		# full paths :-/
		#
		# TODO:
		# Maybe we can use pixtype="pixbuf" with get_pixbuf_icon() somehow...

		self.context_menu_verbs = [
			('Edit', self.launch_edit_app),
			('AboutCardapio', self.open_about_dialog),
			('AboutGnome', self.open_about_dialog),
			('AboutDistro', self.open_about_dialog)
		]

		if self.panel_applet is not None:
			self.panel_applet.connect('destroy', self.quit)

		self.build_ui()


	def build_ui(self):

		self.prepare_colors()

		self.clear_pane(self.application_pane)
		self.clear_pane(self.category_pane)
		self.clear_pane(self.sideapp_pane)
		self.clear_pane(self.left_session_pane)
		self.clear_pane(self.right_session_pane)

		self.section_list = {}
		self.app_list = []

		button = self.add_sidebar_button(_('All'), None, self.category_pane, tooltip = _('Show all categories'))
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_sections_sidebar_button = button 
		self.set_sidebar_button_active(button, True)
		self.all_sections_sidebar_button.set_sensitive(False)

		self.no_results_slab, dummy, self.no_results_label = self.add_application_section('Dummy text')
		self.hide_no_results_text()

		# slabs that should go *before* regular application slabs
		self.add_favorites_slab()
		self.add_places_slab()
		self.add_help_slab()

		self.build_applications_list()

		# slabs that should go *after* regular application slabs
		self.add_session_slab()
		self.add_system_slab()
		self.add_plugin_slabs()

		self.build_favorites_list()
		self.build_places_list()
		self.build_session_list()
		self.build_system_list()
		self.build_help_list()

		self.show_message(False)


	def rebuild_ui(self, show_message = False):

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)
			self.rebuild_timer = None

		if show_message:
			self.show_message(True)

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


	def on_mainwindow_destroy(self, widget):

		self.quit()


	def on_mainwindow_key_press(self, widget, event):

		if self.window.get_focus() != self.search_entry:
			self.previously_focused_widget = self.window.get_focus()


	def on_mainwindow_after_key_press(self, widget, event):

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
		window_x, window_y, window_w, window_h = self.window.get_allocation()

		if window_x <= x <= window_x + window_w and window_y <= y <= window_y + window_h:

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

		if property_changed.name == 'gtk-color-scheme'\
				or property_changed.name == 'gtk-theme-name':
			self.prepare_colors()
			self.schedule_rebuild()


	def schedule_rebuild(self):

		if self.rebuild_timer is not None:
			glib.source_remove(self.rebuild_timer)

		self.rebuild_timer = glib.timeout_add_seconds(self.settings['menu rebuild delay'], self.rebuild_ui)


	def on_menu_data_changed(self, tree):

		self.schedule_rebuild()


	def on_searchentry_icon_press(self, widget, iconpos, event):

		if self.is_searchfield_empty():
			self.show_all_nonempty_sections()

		else:
			self.clear_search_entry()


	def on_searchentry_changed(self, widget):

		text = self.search_entry.get_text().strip()

		self.search_menus(text)

		if len(text) == 0:
			self.hide_all_transitory_sections(fully_hide = True)
			self.hide_no_results_text()

		else:
			self.all_sections_sidebar_button.set_sensitive(True)
			self.no_results_to_show = True


		if self.active_plugins:

			if len(text) >= self.settings['min search string length']:
				self.schedule_search_with_plugin(text)

			else:
				for plugin in self.active_plugins:
					self.set_section_is_empty(plugin.section_slab)
					plugin.section_slab.hide()


	def search_menus(self, text):

		text = text.lower()

		for sec in self.section_list:
			self.set_section_is_empty(sec)

		for app in self.app_list:

			if app['title'].find(text) == -1:
				app['button'].hide()
			else:
				app['button'].show()
				self.set_section_has_entries(app['section'])

		if self.selected_section is None:
			self.show_all_nonempty_sections()
		else:
			self.consider_showing_no_results_text()


	def schedule_search_with_plugin(self, text):

		if self.search_timer_local is not None:
			glib.source_remove(self.search_timer_local)

		if self.search_timer_remote is not None:
			glib.source_remove(self.search_timer_remote)

		delay_type = 'local search update delay'
		delay = self.settings[delay_type]
		self.search_timer_local = glib.timeout_add(delay, self.search_with_plugin, text, delay_type)

		delay_type = 'remote search update delay'
		delay = self.settings[delay_type]
		self.search_timer_remote = glib.timeout_add(delay, self.search_with_plugin, text, delay_type)

		self.search_with_plugin(text, None)


	def search_with_plugin(self, text, delay_type):

		if delay_type == 'local search update delay':
			glib.source_remove(self.search_timer_local)
			self.search_timer_local = None

		elif delay_type == 'remote search update delay':
			glib.source_remove(self.search_timer_remote)
			self.search_timer_remote = None

		for plugin in self.active_plugins:
			if plugin.search_delay_type == delay_type:
				if plugin.is_running: plugin.cancel()
				plugin.is_running = True
				plugin.search(text)

		return False
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def handle_search_error(self, plugin, error):

		plugin.is_running = False
		print('Plugin error: %s' % plugin.name)
		print(error)


	def handle_search_result(self, plugin, results):

		plugin.is_running = False

		if len(self.search_entry.get_text()) < self.settings['min search string length']:

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
		container.remove(plugin.section_contents)
		plugin.section_contents = gtk.VBox()
		container.add(plugin.section_contents)

		for result in results:

			dummy, canonical_path = urllib2.splittype(result['xdg uri'])
			parent_name, child_name = os.path.split(canonical_path)

			icon_name = result['icon name'].replace('/', '-')
			if not self.icon_theme.has_icon(icon_name):
				icon_name = 'text-x-generic'

			button = self.add_launcher_entry(result['name'], icon_name, plugin.section_contents, tooltip = result['tooltip'])
			button.connect('clicked', self.on_xdg_button_clicked, result['xdg uri'])

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

			if self.no_results_to_show:
				self.consider_showing_no_results_text()

		gtk.gdk.threads_leave()


	def is_searchfield_empty(self):

		return (len(self.search_entry.get_text().strip()) == 0)


	def on_searchentry_activate(self, widget):

		for plugin in self.active_plugins:
			if plugin.is_running: plugin.cancel()

		if self.is_searchfield_empty():
			self.hide_all_transitory_sections()
			return 

		first_app_widget = self.get_first_visible_app()
		if first_app_widget is not None:
			first_app_widget.emit('clicked')

		self.clear_search_entry()


	def on_searchentry_key_press_event(self, widget, event):

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

			for plugin in self.active_plugins:
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


	def on_mainwindow_key_press_event(self, widget, event):

		if self.search_entry.is_focus(): return False

		if event.keyval == gtk.gdk.keyval_from_name('Escape'):

			self.clear_search_entry()
			self.window.set_focus(self.search_entry)

		else: return False
		return True


	# make Tab go from first result element to text entry widget
	def on_first_button_key_press_event(self, widget, event):

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

		# update coordinates according to panel orientation
		orientation = self.panel_applet.get_orient()

		if orientation == gnomeapplet.ORIENT_UP or orientation == gnomeapplet.ORIENT_DOWN:
			applet_height = panel_height

		if orientation == gnomeapplet.ORIENT_LEFT or orientation == gnomeapplet.ORIENT_RIGHT:
			applet_width = panel_width

		window_x = panel_x + applet_x
		window_y = panel_y + applet_y + applet_height

		# move window to one edge always matches some edge of the panel button 

		if window_x + window_width > screen_width:
			window_x = panel_x + applet_x + applet_width - window_width

		if window_y + window_height > screen_height:
			window_y = panel_y + applet_y - window_height

		# if it is impossible, do out best to have the top-left corner of our
		# window visible at least

		if window_x < 0: window_x = 0
		if window_y < 0: window_y = 0

		window.move(window_x + offset_x, window_y + offset_y)


	def restore_dimensions(self):

		if self.settings['window size'] is not None: 
			self.window.resize(*self.settings['window size'])


	def save_dimensions(self):

		self.settings['window size'] = self.window.get_size()


	def show_message(self, state = True):

		if state == False:
			self.message_window.hide()
			#self.message_window.set_keep_above(False)
			return

		self.reposition_window(is_message_window = True)
		#self.message_window.set_keep_above(True)
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


	def on_panel_button_press(self, widget, event):
		# used for the menu only

		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
			widget.emit_stop_by_name('button-press-event')
			self.panel_applet.setup_menu(self.context_menu_xml, self.context_menu_verbs, None)


	def on_panel_button_toggled(self, widget, event):

		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 1:

			if self.visible: self.hide()
			else: self.show()

			return True # required! or we get strange focus problems


	def on_panel_change_background(self, widget, type, color, pixmap):

		widget.set_style(None)
		rc_style = gtk.RcStyle()
		self.panel_applet.modify_style(rc_style)

		if (type == gnomeapplet.NO_BACKGROUND):
			pass

		elif (type == gnomeapplet.COLOR_BACKGROUND):
			self.panel_applet.modify_bg(gtk.STATE_NORMAL, color)
			self.panel_button.parent.modify_bg(gtk.STATE_NORMAL, color)

		elif (type == gnomeapplet.PIXMAP_BACKGROUND):
			style = self.panel_applet.style
			style.bg_pixmap[gtk.STATE_NORMAL] = pixmap
			self.panel_applet.set_style(style)  
			self.panel_button.parent.set_style(style) # TODO: make this transparent?


	def on_applet_realize(self, widget):

		panel = self.panel_applet.get_toplevel().window
		panel_width, panel_height = panel.get_size()
		applet_x, applet_y, applet_width, applet_height = self.panel_button.get_allocation()
	
		#orientation = self.panel_applet.get_orient()
	
		#if orientation == gnomeapplet.ORIENT_UP or orientation == gnomeapplet.ORIENT_DOWN:
		#	self.panel_button.set_size_request(-1, panel_height)
	
		#if orientation == gnomeapplet.ORIENT_LEFT or orientation == gnomeapplet.ORIENT_RIGHT:
		#	self.panel_button.set_size_request(panel_width, -1)


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

			button = self.add_launcher_entry(item[1], item[3], item[4], tooltip = item[2], app_list = self.app_list)
			button.connect('clicked', self.on_raw_button_clicked, item[0])


	def build_places_list(self):

		button = self.add_launcher_entry(_('Home'), 'user-home', self.places_section_contents, tooltip = _('Open your personal folder'), app_list = self.app_list)
		button.connect('clicked', self.on_xdg_button_clicked, self.user_home_folder)

		button = self.add_launcher_entry(_('Computer'), 'computer', self.places_section_contents, tooltip = _('Browse all local and remote disks and folders accessible from this computer'), app_list = self.app_list)
		button.connect('clicked', self.on_xdg_button_clicked, 'computer:///')

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

		button = self.add_launcher_entry(_('Trash'), 'user-trash', self.places_section_contents, tooltip = _('Open the trash'), app_list = self.app_list)
		button.connect('clicked', self.on_xdg_button_clicked, 'trash:///')


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

		button = self.add_launcher_entry(folder_name, folder_icon, self.places_section_contents, tooltip = folder_path, app_list = self.app_list)
		button.connect('clicked', self.on_xdg_button_clicked, folder_path)


	def build_favorites_list(self):

		have_no_favorites = self.add_tree_to_app_list(self.app_tree.root, self.favorites_section_contents, recursive = False)
		if have_no_favorites:
			self.hide_section(self.favorites_section_slab, fully_hide = True)


	def build_session_list(self):

		dbus_services = self.bus.list_names()
		can_lock_screen = 'org.gnome.ScreenSaver' in dbus_services
		can_manage_session = 'org.gnome.SessionManager' in dbus_services

		if can_lock_screen:

			# TODO: not working! this is freezing the app!

			button_label = _('Lock Screen')
			button_tooltip = _('Protect your computer from unauthorized use')
			button = self.add_launcher_entry(button_label, 'system-lock-screen', self.session_section_contents, tooltip = button_tooltip, app_list = self.app_list)
			button.connect('clicked', self.on_lockscreen_button_clicked)

			if self.settings['show session buttons']:
				button = self.add_button(button_label, 'system-lock-screen', self.left_session_pane, tooltip = button_tooltip, is_launcher_button = True)
				button.connect('clicked', self.on_lockscreen_button_clicked)


		if can_manage_session:

			button_label = _('Log Out...')
			button_tooltip = _('Log out of this session to log in as a different user')
			button = self.add_launcher_entry(button_label, 'system-log-out', self.session_section_contents, tooltip = button_tooltip, app_list = self.app_list)
			button.connect('clicked', self.on_logout_button_clicked)

			if self.settings['show session buttons']:
				button = self.add_button(button_label, 'system-log-out', self.right_session_pane, tooltip = button_tooltip, is_launcher_button = True)
				button.connect('clicked', self.on_logout_button_clicked)

			button_label = _('Shut Down...')
			button_tooltip = _('Shut down the system')
			button = self.add_launcher_entry(button_label, 'system-shutdown', self.session_section_contents, tooltip = button_tooltip, app_list = self.app_list)
			button.connect('clicked', self.on_shutdown_button_clicked)

			if self.settings['show session buttons']:
				button = self.add_button(button_label, 'system-shutdown', self.right_session_pane, tooltip = button_tooltip, is_launcher_button = True)
				button.connect('clicked', self.on_shutdown_button_clicked)

		if self.settings['show session buttons'] and (can_lock_screen or can_manage_session):
			self.session_pane.show()
		else:
			self.session_pane.hide()


	def build_system_list(self):

		for node in self.sys_tree.root.contents:

			if isinstance(node, gmenu.Entry):

				button = self.add_sidebar_button(node.name, node.icon, self.sideapp_pane, tooltip = node.get_comment(), use_toggle_button = False)
				button.connect('clicked', self.on_app_button_clicked, node.desktop_file_path)

		self.add_tree_to_app_list(self.sys_tree.root, self.system_section_contents)


	def build_applications_list(self):

		for node in self.app_tree.root.contents:

			if isinstance(node, gmenu.Directory):

				# add to main pane
				self.add_slab(node.name, node.icon, node.get_comment(), node = node, hide = False)


	def add_slab(self, title_str, icon_name = None, tooltip = '', hide = False, node = None):

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
			self.section_list[section_slab] = {'has-entries': False, 'category': sidebar_button, 'contents': section_contents, 'title': title_str}

		else:
			self.section_list[section_slab] = {'has-entries': True, 'category': sidebar_button, 'contents': section_contents, 'title': title_str}

		return section_slab, section_contents


	def add_help_slab(self):

		section_slab, section_contents = self.add_slab(_('Help'), 'system-help', hide = True)
		self.help_section_slab = section_slab
		self.help_section_contents = section_contents


	def add_places_slab(self):

		section_slab, section_contents = self.add_slab(_('Places'), 'folder', tooltip = _('Access documents and folders'), hide = False)
		self.places_section_contents = section_contents


	def add_favorites_slab(self):

		section_slab, section_contents = self.add_slab(_('Pinned items'), 'emblem-favorite', tooltip = _('Your favorite applications'), hide = False)
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


	def add_plugin_slabs(self):

		self.plugin_section_slabs = []

		for plugin in self.active_plugins:

			section_slab, section_contents = self.add_slab(plugin.category_name, plugin.category_icon, hide = plugin.hide_from_sidebar)
			plugin.section_slab = section_slab
			plugin.section_contents = section_contents


	def clear_pane(self, container):

		for	child in container.get_children():
			container.remove(child)


	def clear_search_entry(self):

		self.search_entry.set_text('')
		self.hide_all_transitory_sections()


	def add_sidebar_button(self, button_str, icon_name, parent_widget, tooltip = '', use_toggle_button = True):

		return self.add_button(button_str, icon_name, parent_widget, tooltip, use_toggle_button = use_toggle_button, is_launcher_button = False)


	def add_launcher_entry(self, button_str, icon_name, parent_widget, tooltip = '', app_list = None):

		button = self.add_button(button_str, icon_name, parent_widget, tooltip, is_launcher_button = True)

		if app_list is not None:
			app_list.append({'title': button_str.lower(), 'button': button, 'section': parent_widget.parent.parent})
			# save the app name, its button, and the section slab it came from
			# NOTE: IF THERE ARE CHANGES IN THE UI FILE, THIS MAY PRODUCE
			# HARD-TO-FIND BUGS!!

		return button


	def add_button(self, button_str, icon_name, parent_widget, tooltip = '', use_toggle_button = None, is_launcher_button = True):

		if is_launcher_button or use_toggle_button == False:
			button = gtk.Button()
		else:
			button = gtk.ToggleButton()

		button_str = self.unescape(button_str)
		tooltip = self.unescape(tooltip)

		label = gtk.Label(button_str)

		if is_launcher_button:
			icon_size = self.icon_size_app
			label.modify_fg(gtk.STATE_NORMAL, self.style_app_button_fg)
		else:
			icon_size = self.icon_size_category

		icon_pixbuf = self.get_pixbuf_icon(icon_name, icon_size)

		hbox = gtk.HBox()
		hbox.add(gtk.image_new_from_pixbuf(icon_pixbuf))
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

		builder = gtk.Builder()
		builder.add_from_file(self.uifile)
		section_slab = builder.get_object('SectionSlab')
		section_contents = builder.get_object('SectionContents')

		if section_slab.parent is not None:
			section_slab.parent.remove(section_slab)

		del builder
		return section_slab, section_contents


	def get_pixbuf_icon(self, icon_value, icon_size, fallback_icon = 'application-x-executable'):

		if not icon_value: icon_value = fallback_icon

		if os.path.isabs(icon_value):
			if os.path.isfile(icon_value):
				try:
					return gtk.gdk.pixbuf_new_from_file_at_size(icon_value, icon_size, icon_size)
				except glib.GError:
					return None
			icon_name = os.path.basename(icon_value)
		else:
			icon_name = icon_value

		if re.match('.*\.(png|xpm|svg)$', icon_name) is not None:
			icon_name = icon_name[:-4]

		try:
			self.icon_theme.handler_block_by_func(self.on_icon_theme_changed)
			return self.icon_theme.load_icon(icon_name, icon_size, gtk.ICON_LOOKUP_FORCE_SIZE)
		except:
			for dir in BaseDirectory.xdg_data_dirs:
				for i in ('pixmaps', 'icons'):
					path = os.path.join(dir, i, icon_value)
					if os.path.isfile(path):
						return gtk.gdk.pixbuf_new_from_file_at_size(path, icon_size, icon_size)
		finally:
			self.icon_theme.handler_unblock_by_func(self.on_icon_theme_changed)

		return self.get_pixbuf_icon(fallback_icon, icon_size)


	def add_tree_to_app_list(self, tree, parent_widget, recursive = True):

		has_no_leaves = True

		for node in tree.contents:

			if isinstance(node, gmenu.Entry):

				button = self.add_launcher_entry(node.name, node.icon, parent_widget, tooltip = node.get_comment(), app_list = self.app_list)
				button.connect('clicked', self.on_app_button_clicked, node.desktop_file_path)
				has_no_leaves = False

			elif isinstance(node, gmenu.Directory) and recursive:

				self.add_tree_to_app_list(node, parent_widget)

		return has_no_leaves


	def prepare_colors(self):

		dummy_window = gtk.Window()
		dummy_window.realize()
		app_style = dummy_window.get_style()
		self.style_app_button_bg = app_style.base[gtk.STATE_NORMAL]
		self.style_app_button_fg = app_style.text[gtk.STATE_NORMAL]
		self.get_object('ScrolledViewport').modify_bg(gtk.STATE_NORMAL, self.style_app_button_bg)


	def launch_edit_app(self, widget, verb):

		for app in  Cardapio.menu_editing_apps:
			if self.launch_raw(app): return

		print(_('No menu editing apps found! Tried these: %s') % ', '.join(Cardapio.menu_editing_apps))


	def on_app_button_clicked(self, widget, desktop_path):

		if os.path.exists(desktop_path):

			path = DesktopEntry.DesktopEntry(desktop_path).getExec()

			# Strip last part of path if it contains %<a-Z>
			match = self.exec_pattern.match(path)

			if match is not None:
				path = match.group(1)

			return self.launch_raw(path)


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
			if self.section_list[sec]['has-entries']:
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

		"""
		Show the "No Results" text if there's no selected section, or if the
		selected section is "Other results"
		"""

		if self.selected_section is None:

			if self.no_results_to_show:
				self.show_no_results_text()

			return 
			
		if self.section_list[self.selected_section]['has-entries']:
			self.selected_section.show()
			self.hide_no_results_text()

		else:
			self.selected_section.hide()
			self.show_no_results_text(_('No results to show in "%(category_name)s"') % {'category_name': self.section_list[self.selected_section]['title']})


	def hide_all_transitory_sections(self, fully_hide = False):

		self.hide_section(self.help_section_slab   , fully_hide)
		self.hide_section(self.session_section_slab, fully_hide)
		self.hide_section(self.system_section_slab , fully_hide)
		
		self.hide_plugin_sections(fully_hide)


	def hide_section(self, section_slab, fully_hide = False):

		if fully_hide:
			self.section_list[section_slab]['has-entries'] = False
			self.section_list[section_slab]['category'].hide()

		section_slab.hide()


	def hide_plugin_sections(self, fully_hide = False):

		for plugin in self.active_plugins:
			if plugin.hide_from_sidebar:
				self.hide_section(plugin.section_slab, fully_hide)


	def set_section_has_entries(self, section_slab):

		self.section_list[section_slab]['has-entries'] = True
		self.section_list[section_slab]['category'].show()


	def set_section_is_empty(self, section_slab):

		self.section_list[section_slab]['has-entries'] = False
		self.section_list[section_slab]['category'].hide()


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
	name               = ''
	description        = ''
	version            = ''

	plugin_api_version = 1.0

	# one of: None, 'local search update delay', 'remote search update delay'
	search_delay_type  = 'local search update delay'

	category_name      = '' # use gettext for category
	category_icon      = ''
	hide_from_sidebar  = True

	is_running = False

	def __init__(self, settings, handle_search_result, handle_search_error):
		"""
		This constructor gets called whenever a plugin is activated.
		(Typically once per session, unless the user is turning plugins on/off)
		
		Note: DO NOT WRITE ANYTHING IN THE settings DICT!!
		"""
		pass


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
		field. It must output a list where each item is a dicts following format
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


def return_true(*dummy):
	return True


def applet_factory(applet, iid):

	button = gtk.ImageMenuItem()

	cardapio = Cardapio(hidden = True, panel_button = button, panel_applet = applet)

	button.set_label(cardapio.settings['applet label'])
	button.set_tooltip_text(_('Access applications, folders, system settings, etc.'))
	button_icon = gtk.image_new_from_icon_name('distributor-logo', gtk.ICON_SIZE_SMALL_TOOLBAR)
	button.set_image(button_icon)

	menu = gtk.MenuBar()
	menu.set_name('CardapioAppletMenu')
	menu.add(button)

	button.connect('button-press-event', cardapio.on_panel_button_toggled)
	menu.connect('button-press-event', cardapio.on_panel_button_press)

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

	applet.connect('change-background', cardapio.on_panel_change_background)
	applet.connect('realize', cardapio.on_applet_realize)
	applet.add(menu)

	applet.show_all()

	return True


