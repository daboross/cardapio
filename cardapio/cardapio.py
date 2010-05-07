#!/usr/bin/env python
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

try:
	import os
	import re
	import sys
	import gtk
	import gio
	import glib
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

except Exception, exception:
	print exception
	sys.exit(1)


APP = 'Cardapio'
DIR = 'locale'

locale.setlocale(locale.LC_ALL, '')
gettext.bindtextdomain(APP, DIR)
gettext.textdomain(APP)
_ = gettext.gettext

# Before version 1.0:
# TODO: make apps draggable to make shortcuts elsewhere, such as desktop or docky
# TODO: add computer, mount points, trash to "places"
# TODO: make sure colors work with all themes
# TODO: make applet 1px larger in every direction, so fitts law works
# TODO: fix metacity's focus problems...
# TODO: handle left and right panel orientations (rotate menuitem), and change-orient signal
# TODO: fix bugs with "no results to show"

# After version 1.0:
# TODO: make a configuration window to change the shortcut, etc. Save with gconf or use ini file
# TODO: remember last window size (using gconf or whatever)
# TODO: make "places" use custom icons
# TODO: fix Win+Space untoggle
# TODO: fix tabbing of first_app_widget / first_result_widget  
# TODO: alt-1, alt-2, ..., alt-9, alt-0 should activate categories
# TODO: any letter or number typed anywhere (without modifiers) is redirected to search entry
# TODO: show context-menu for mountpoints to eject
# TODO: multiple columns when window is wide enough (like gnome-control-center)
# TODO: slash "/" should navigate inside folders, Esc pops out
# TODO: search results have context menu with "Open with...", "Show parent folder", and so on.
# plus other TODO's elsewhere in the code

class Cardapio(dbus.service.Object):


	menu_rebuild_delay       = 3    # seconds
	min_search_string_length = 3    # characters
	search_results_limit     = 15   # results
	search_update_delay      = 100  # msec

	default_panel_label = commands.getoutput('lsb_release -is')
	default_keybinding = '<Super>space'
	# try gtk.accelerator_parse('<Super>space') to see if the string is correct!

	file_management_apps = ('nautilus', 'thunar')
	menu_editing_apps = ('alacarte', 'gmenu-simple-editor')

	bus_name_str = 'org.varal.Cardapio'
	bus_obj_str  = '/org/varal/Cardapio'


	def __init__(self, hidden = False, panel_applet = None, panel_button = None):

		self.user_home_folder = os.path.expanduser('~')

		self.panel_applet = panel_applet
		self.panel_button = panel_button
		self.auto_toggled_sidebar_button = False

		self.app_list = []
		self.section_list = {}
		self.selected_section = None

		self.first_app_widget = None
		self.first_result_widget = None
		self.no_results_to_show = False

		self.visible = False
		self.window_size = None

		self.app_tree = gmenu.lookup_tree('applications.menu')
		self.sys_tree = gmenu.lookup_tree('settings.menu')

		# TODO: internationalize these
		self.exec_pattern = re.compile("^(.*?)\s+\%[a-zA-Z]$")
		self.sanitize_query_pattern = re.compile("[^a-zA-Z0-9]")

		self.set_up_dbus()
		self.set_up_tracker_search()
		self.build_ui()
		self.first_app_widget = self.app_list[0]['button']

		self.app_tree.add_monitor(self.on_menu_data_changed)
		self.sys_tree.add_monitor(self.on_menu_data_changed)

		self.keybinding = Cardapio.default_keybinding
		keybinder.bind(self.keybinding, self.show_hide)

		if not hidden: self.show()


	def set_up_dbus(self):

		DBusGMainLoop(set_as_default=True)
		self.bus = dbus.SessionBus()
		dbus.service.Object.__init__(self, self.bus, Cardapio.bus_obj_str)


	def set_up_tracker_search(self):

		self.tracker = None
		self.search_timer = None

		if self.bus.request_name('org.freedesktop.Tracker1') == dbus.bus.REQUEST_NAME_REPLY_IN_QUEUE:
			tracker_object = self.bus.get_object('org.freedesktop.Tracker1', '/org/freedesktop/Tracker1/Resources')
			self.tracker = dbus.Interface(tracker_object, 'org.freedesktop.Tracker1.Resources') 


	def on_session_action(self, widget, shutdown):

		sm_proxy = self.bus.get_object('org.gnome.SessionManager', '/org/gnome/SessionManager')
		sm_if = dbus.Interface(sm_proxy, 'org.gnome.SessionManager')

		if shutdown : sm_if.Shutdown()
		else        : sm_if.Logout(0)

		self.hide()


	def on_lock_screen_activated(self, widget):

		self.hide()

		try:
			ss_proxy = self.bus.get_object('org.gnome.ScreenSaver', '/')
			dbus.Interface(ss_proxy, 'org.gnome.ScreenSaver').Lock()

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


	def build_ui(self):

		cardapio_path = os.path.dirname(__file__)
		self.uifile = os.path.join(cardapio_path, 'cardapio.ui')

		self.builder = gtk.Builder()
		self.builder.add_from_file(self.uifile)
		self.builder.connect_signals(self)

		self.get_object = self.builder.get_object
		self.window            = self.get_object('MainWindow')
		self.about_dialog      = self.get_object('AboutDialog')
		self.application_pane  = self.get_object('ApplicationPane')
		self.category_pane     = self.get_object('CategoryPane')
		self.system_pane       = self.get_object('SystemPane')
		self.search_entry      = self.get_object('SearchEntry')
		self.scrolled_window   = self.get_object('ScrolledWindow')
		self.scroll_adjustment = self.scrolled_window.get_vadjustment()

		self.icon_theme = gtk.icon_theme_get_default()
		self.icon_theme.connect('changed', self.on_icon_theme_changed)
		self.icon_size_large = gtk.icon_size_lookup(gtk.ICON_SIZE_LARGE_TOOLBAR)[0]
		self.icon_size_small = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)[0]

		# make sure buttons have icons!
		settings = gtk.settings_get_default()
		settings.set_property('gtk-button-images', True)

		self.window.set_keep_above(True)

		self.context_menu_xml = '''
			<popup name="button3">
				<menuitem name="Item 1" verb="Edit" label="%s" pixtype="stock" pixname="gtk-edit"/>
				<menuitem name="Item 2" verb="About" label="%s" pixtype="stock" pixname="gtk-about"/>
			</popup>
			''' % (_('_Edit Menus'), _('_About'))

		self.context_menu_verbs = [
				('Edit', self.launch_edit_app),
				('About', self.open_about_dialog)
				]

		self.prepare_viewport()
		self.rebuild()

	
	def open_about_dialog(self, widget, verb):

		self.about_dialog.show()


	def on_about_dialog_close(self, widget, response = None):

		self.about_dialog.hide()


	def on_mainwindow_destroy(self, widget):

		gtk.main_quit()


	def on_mainwindow_focus_out(self, widget, event):

		#if self.panel_applet is None:
		#	self.hide()
		
		if gtk.gdk.window_at_pointer() is None:
			# make sure clicking the applet button does cause a focus-out event
			self.hide()


	def on_mainwindow_delete_event(self, widget, event):

		if self.panel_applet:
			# keep window alive if in panel mode
			return True


	def on_mainwindow_configure_event(self, widget, event):

		self.save_dimensions()


	def on_icon_theme_changed(self, icon_theme):

		glib.timeout_add_seconds(Cardapio.menu_rebuild_delay, self.rebuild)


	def on_menu_data_changed(self, tree):

		glib.timeout_add_seconds(Cardapio.menu_rebuild_delay, self.rebuild)


	def on_searchentry_icon_press(self, widget, iconpos, event):

		if self.is_searchfield_empty():
			self.show_all_nonempty_sections()

		else:
			self.clear_search_entry()


	def on_searchentry_changed(self, widget):

		self.first_app_widget = None
		self.first_result_widget = None

		text = self.search_entry.get_text().strip()

		self.search_menus(text)

		if len(text) == 0:
			self.disappear_with_section(self.session_section_slab)
			self.disappear_with_section(self.system_section_slab)
			self.disappear_with_section(self.search_section_slab)
			self.hide_no_results_text()

		else:
			self.all_sections_sidebar_button.set_sensitive(True)

		if self.tracker is not None:
			if len(text) >= Cardapio.min_search_string_length:
				self.schedule_search_with_tracker(text)
			else:
				self.search_section_slab.hide()


	def search_menus(self, text):

		text = text.lower()
		self.first_app_widget = None

		for sec in self.section_list:
			self.set_section_is_empty(sec)

		for app in self.app_list:

			if app['title'].find(text) == -1:
				app['button'].hide()
			else:
				app['button'].show()
				self.set_section_has_entries(app['section'])

				if self.first_app_widget is None:
					self.first_app_widget = app['button']

		if self.selected_section is None:
			self.show_all_nonempty_sections()
		else:
			self.consider_showing_no_results_text()


	def schedule_search_with_tracker(self, text):

		if self.search_timer is not None:
			glib.source_remove(self.search_timer)

		self.search_timer = glib.timeout_add(Cardapio.search_update_delay, self.search_with_tracker, text)


	def search_with_tracker(self, text):

		glib.source_remove(self.search_timer)

		# no .lower(), since there's no fn:lower-case in tracker
		#text = self.escape_quotes(text).lower()
		text = self.escape_quotes(text)

		self.tracker.SparqlQuery(
			"""
				SELECT ?title ?uri ?tooltip ?mime
				WHERE { 
					?item a nfo:FileDataObject;
						nfo:fileName ?title;
						nie:url ?uri;
						nie:mimeType ?mime;
						nfo:belongsToContainer ?parent.
					?parent nie:url ?tooltip.
					FILTER (fn:contains(?title, '%s'))
					}
				LIMIT %d
			""" 
			% (text, Cardapio.search_results_limit),
			dbus_interface='org.freedesktop.Tracker1.Resources',
			reply_handler=self.handle_search_result,
			error_handler=self.handle_search_error
			)

		# Things I've tried:
		#
		#			FILTER (fn:contains(?title, '%s'))
		#
		#			FILTER (regex(?title, '%s', 'i'))
		#
		#			?item fts:match '%s'.
		#			ORDER BY DESC(fts:rank(?item))
		#

		# Tracker issues:
		#
		# - no support for fn:lower-case, so i can't do:
		#
		#       FILTER (fn:contains(fn:lower-case(?title), '%s'))
		#
		# - fts:match does not match source code! so not good for searching
		# files in general, only documents.
		#
		# - regex works, but it's too slow for normal use...


	def is_searchfield_empty(self):

		return (len(self.search_entry.get_text().strip()) == 0)


	def on_searchentry_activate(self, widget):

		if self.is_searchfield_empty():
			self.system_section_slab.hide()
			self.session_section_slab.hide()
			self.search_section_slab.hide()
			return 

		if self.first_app_widget is not None:
			self.first_app_widget.emit('clicked')

		elif self.first_result_widget is not None:
			self.first_result_widget.emit('clicked')

		self.clear_search_entry()


	def on_searchentry_key_press_event(self, widget, event):

		# make Tab go to first result element
		if event.keyval == gtk.gdk.keyval_from_name('Tab'):

			if self.selected_section is not None:

				contents = self.section_list[self.selected_section]['contents']
				visible_children = [c for c in contents.get_children() if c.get_property('visible')]

				if visible_children:

					#self.first_child.connect('key-press-event', self.on_first_button_key_press_event)
					self.window.set_focus(visible_children[0])
				
			elif self.first_app_widget is not None:

				#self.first_app_widget.connect('key-press-event', self.on_first_button_key_press_event)
				self.window.set_focus(self.first_app_widget)

			elif self.first_result_widget is not None:

				#self.first_result_widget.connect('key-press-event', self.on_first_button_key_press_event)
				self.window.set_focus(self.first_result_widget)

		elif event.keyval == gtk.gdk.keyval_from_name('Escape'):

			if not self.is_searchfield_empty():

				self.clear_search_entry()

			elif self.selected_section is not None:

				self.show_all_nonempty_sections()

			else:
				self.hide()

		else: return False
		return True


	def on_mainwindow_key_press_event(self, widget, event):

		if self.search_entry.is_focus(): return False

		if event.keyval == gtk.gdk.keyval_from_name('Escape'):

			self.clear_search_entry()
			self.window.set_focus(self.search_entry)

		else: return False
		return True

		# TODO: send all alphanumeric keys to entry field
		# (or all non-tab, non-shift-tab, non-enter, non-esc, non-modifier keys)


	# make Tab go from first result element to text entry widget
	def on_first_button_key_press_event(self, widget, event):

		if event.keyval == gtk.gdk.keyval_from_name('ISO_Left_Tab'):

			self.window.set_focus(self.search_entry)

		else: return False
		return True


	def restore_location(self):

		menu_width, menu_height = self.window.get_size()
		screen_height = gtk.gdk.screen_height()
		screen_width  = gtk.gdk.screen_width()

		if self.panel_applet is None:
			menu_x = (screen_width - menu_width)/2
			menu_y = (screen_height - menu_height)/2
			self.window.move(menu_x, menu_y)
			return

		panel = self.panel_button.get_parent_window()
		panel_x, panel_y = panel.get_origin()
		panel_width, panel_height = panel.get_size()

		applet_x, applet_y, applet_width, applet_height = self.panel_button.get_allocation()

		# update coordinates according to panel orientation
		orientation = self.panel_applet.get_orient()

		if orientation == gnomeapplet.ORIENT_UP or orientation == gnomeapplet.ORIENT_DOWN:
			applet_height = panel_height
		
		if orientation == gnomeapplet.ORIENT_LEFT or orientation == gnomeapplet.ORIENT_RIGHT:
			applet_width = panel_width

		menu_x = panel_x + applet_x
		menu_y = panel_y + applet_y + applet_height

		# move window to one edge always matches some edge of the panel button 

		if menu_x + menu_width > screen_width:
			menu_x = panel_x + applet_x + applet_width - menu_width

		if menu_y + menu_height > screen_height:
			menu_y = panel_y + applet_y - menu_height

		# if it is impossible, do out best to have the top-left corner of our
		# window visible at least

		if menu_x < 0: menu_x = 0
		if menu_y < 0: menu_y = 0

		self.window.move(menu_x, menu_y)



	def restore_dimensions(self):

		if self.window_size is not None: 
			self.window.resize(*self.window_size)


	def save_dimensions(self):

		self.window_size = self.window.get_size()


	def show(self):

		self.restore_dimensions()
		self.restore_location()

		self.auto_toggle_panel_button(True)

		self.window.set_focus(self.search_entry)
		self.window.show()

		self.visible = True


	def hide(self):

		self.auto_toggle_panel_button(False)

		self.window.hide()
		self.visible = False

		self.clear_search_entry()
		self.show_all_nonempty_sections()


	@dbus.service.method(dbus_interface=bus_name_str, in_signature=None, out_signature=None)
	def show_hide(self):

		if self.visible: self.hide()
		else: self.show()


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
			self.panel_button.parent.set_style(style)  


	def auto_toggle_panel_button(self, state):

		if self.panel_applet is not None:
			#self.panel_button.set_active(state)
			if state: self.panel_button.select()
			else: self.panel_button.deselect()


	def rebuild(self):

		self.clear_application_pane()
		self.clear_category_pane()
		self.clear_system_pane()

		self.section_list = {}
		self.app_list = []

		button = self.add_sidebar_button(_('All'), None, self.category_pane, comment = _('Show all categories'))
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_sections_sidebar_button = button 
		self.set_sidebar_button_active(button, True)
		self.all_sections_sidebar_button.set_sensitive(False)

		self.no_results_slab, dummy, self.no_results_label = self.add_application_section('Dummy text')
		self.hide_no_results_text()

		self.add_places_slab()
		self.add_applications_slab()
		self.add_hidden_session_slab()
		self.add_hidden_system_slab()
		self.add_hidden_search_results_slab()

		return False 
		# Required! makes this a "one-shot" timer, rather than "periodic"


	def build_places_list(self):

		button = self.add_launcher_entry(_('Home'), 'user-home', self.places_section_contents, comment = _('Open your personal folder'), app_list = self.app_list)
		button.connect('clicked', self.on_xdg_button_clicked, self.user_home_folder)

		xdg_folders_filepath = os.path.join(DesktopEntry.xdg_config_home, 'user-dirs.dirs')
		xdg_folders_file = file(xdg_folders_filepath, 'r')

		for line in xdg_folders_file.readlines():

			res = re.match('\s*XDG_DESKTOP_DIR\s*=\s*"(.+)"', line)
			if res is not None:
				path = res.groups()[0]
				self.add_place(_('Desktop'), path, 'user-desktop')

		xdg_folders_file.close()

		bookmark_filepath = os.path.join(self.user_home_folder, '.gtk-bookmarks')
		bookmark_file = file(bookmark_filepath, 'r')

		for line in bookmark_file.readlines():
			if line.strip(' \n\r\t'):
				name, path = self.get_place_name_and_path(line)
				# TODO: make sure path exists
				# TODO: if path doesn't exist, add gio monitor (could be a removable disk)
				self.add_place(name, path, 'folder')

		bookmark_file.close()

		self.bookmark_monitor = gio.File(bookmark_filepath).monitor_file()  # keep a reference to avoid getting it garbage collected
		self.bookmark_monitor.connect('changed', self.on_bookmark_monitor_changed)


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
		button = self.add_launcher_entry(folder_name, folder_icon, self.places_section_contents, comment = folder_path, app_list = self.app_list)
		button.connect('clicked', self.on_xdg_button_clicked, folder_path)


	def build_session_list(self):

		dbus_services = self.bus.list_names()
		can_lock_screen = 'org.gnome.ScreenSaver' in dbus_services
		can_manage_session = 'org.gnome.SessionManager' in dbus_services

		if can_lock_screen:

			# TODO: not working! this is freezing the app!

			#button = self.add_launcher_entry(_('Lock Screen'), 'system-lock-screen', self.session_section_contents, comment = _('Protect your computer from unauthorized use'), app_list = self.app_list)
			#button.connect('clicked', self.on_lock_screen_activated)

			pass

		if can_manage_session:

			button = self.add_launcher_entry(_('Log Out...'), 'system-log-out', self.session_section_contents, comment = _('Log out of this session to log in as a different user'), app_list = self.app_list)
			button.connect('clicked', self.on_session_action, False)

			button = self.add_launcher_entry(_('Shut Down...'), 'system-shutdown', self.session_section_contents, comment = _('Shut down the system'), app_list = self.app_list)
			button.connect('clicked', self.on_session_action, True)


	def add_applications_slab(self):

		for node in self.app_tree.root.contents:

			if isinstance(node, gmenu.Directory):

				# add to main pane
				self.add_section_slab(node)

			elif isinstance(node, gmenu.Entry):

				# add to system pane
				button = self.add_sidebar_button(node.name, node.icon, self.system_pane, comment = node.get_comment(), use_toggle_button = False)
				button.connect('clicked', self.on_app_button_clicked, node.desktop_file_path)


	def add_section_slab(self, node):

		# add category to category pane
		sidebar_button = self.add_sidebar_button(node.name, node.icon, self.category_pane, comment = node.get_comment())

		# add category to application pane
		section_slab, section_contents, dummy = self.add_application_section(node.name)

		# add all apps in this category to application pane
		self.add_tree_to_app_list(node, section_contents)

		sidebar_button.connect('clicked', self.on_sidebar_button_clicked, section_slab)
		self.section_list[section_slab] = {'has-entries': True, 'category': sidebar_button, 'contents': section_contents, 'title': node.name}


	def add_slab(self, title_str, icon_name = None, comment = '', hide = True):

		# add category to category pane
		sidebar_button = self.add_sidebar_button(title_str, icon_name, self.category_pane, comment = comment)

		# add category to application pane
		section_slab, section_contents, dummy = self.add_application_section(title_str)

		sidebar_button.connect('clicked', self.on_sidebar_button_clicked, section_slab)

		if hide:
			sidebar_button.hide()
			section_slab.hide()
			self.section_list[section_slab] = {'has-entries': False, 'category': sidebar_button, 'contents': section_contents, 'title': title_str}
		else:
			self.section_list[section_slab] = {'has-entries': True, 'category': sidebar_button, 'contents': section_contents, 'title': title_str}

		return section_slab, section_contents


	def add_places_slab(self):

		section_slab, section_contents = self.add_slab(_('Places'), 'folder', hide = False)
		self.places_section_slab = section_slab
		self.places_section_contents = section_contents
		self.build_places_list()


	def add_hidden_session_slab(self):

		section_slab, section_contents = self.add_slab(_('Session'), 'session-properties')
		self.session_section_slab = section_slab
		self.session_section_contents = section_contents
		self.build_session_list()


	def add_hidden_system_slab(self):

		section_slab, section_contents = self.add_slab(_('System'), 'applications-system')

		self.add_tree_to_app_list(self.app_tree.root, section_contents, recursive = False)
		self.add_tree_to_app_list(self.sys_tree.root, section_contents)

		self.system_section_slab = section_slab


	def add_hidden_search_results_slab(self):

		# add system category to application pane
		section_slab, section_contents = self.add_slab(_('Other Results'), 'system-search')
		self.search_section_slab = section_slab
		self.search_section_contents = section_contents


	def clear_application_pane(self):

		container = self.get_object('ApplicationPane')
		for	child in container.get_children():
			container.remove(child)


	def clear_category_pane(self):

		container = self.get_object('CategoryPane')
		for	child in container.get_children():
			container.remove(child)


	def clear_system_pane(self):

		container = self.get_object('SystemPane')
		for	child in container.get_children():
			container.remove(child)


	def clear_search_entry(self):

		self.search_entry.set_text('')
		self.system_section_slab.hide()
		self.session_section_slab.hide()
		self.search_section_slab.hide()


	def add_sidebar_button(self, button_str, icon_name, parent_widget, comment = '', use_toggle_button = True):

		return self.add_button(button_str, icon_name, parent_widget, comment, icon_size = self.icon_size_small, use_toggle_button = use_toggle_button)


	def add_launcher_entry(self, button_str, icon_name, parent_widget, comment = '', app_list = None):

		button = self.add_button(button_str, icon_name, parent_widget, comment, icon_size = self.icon_size_large)

		if app_list is not None:
			app_list.append({'title': button_str.lower(), 'button': button, 'section': parent_widget.parent.parent})
			# save the app name, its button, and the section slab it came from
			# NOTE: IF THERE ARE CHANGES IN THE UI FILE, THIS MAY PRODUCE
			# HARD-TO-FIND BUGS!!

		return button


	def add_button(self, button_str, icon_name, parent_widget, comment = '', icon_size = 32, use_toggle_button = False):

		if use_toggle_button:
			button = gtk.ToggleButton(button_str)
		else:
			button = gtk.Button(button_str)

		icon_pixbuf = self.get_pixbuf_icon(icon_name, icon_size)
		button.set_image(gtk.image_new_from_pixbuf(icon_pixbuf))

		if comment: button.set_tooltip_text(comment)

		button.set_alignment(0, 0.5)
		button.set_relief(gtk.RELIEF_NONE)
		button.set_use_underline(False)

		button.show()
		parent_widget.pack_start(button, expand = False, fill = False)

		return button


	def add_application_section(self, section_title = None):

		# TODO: make sure the section titles use a text color that works against
		# all base colors

		section_slab, section_contents = self.add_section()

		if section_title is not None:
			label = section_slab.get_label_widget()
			label.set_text(section_title)

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


	def get_pixbuf_icon(self, icon_value, icon_size, default_icon = 'application-x-executable'):

		if not icon_value: icon_value = default_icon

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

		return self.get_pixbuf_icon(default_icon, icon_size)


	def add_tree_to_app_list(self, tree, parent_widget, recursive = True):

		for node in tree.contents:

			# TODO: make sure these buttons use a text color that works against
			# all base colors

			if isinstance(node, gmenu.Entry):

				button = self.add_launcher_entry(node.name, node.icon, parent_widget, comment = node.get_comment(), app_list = self.app_list)
				button.connect('clicked', self.on_app_button_clicked, node.desktop_file_path)

			elif isinstance(node, gmenu.Directory) and recursive:

				self.add_tree_to_app_list(node, parent_widget)


	def handle_search_error(self, error):

		print error


	def handle_search_result(self, results):

		container = self.search_section_contents.parent
		container.remove(self.search_section_contents)
		self.search_section_contents = gtk.VBox()
		container.add(self.search_section_contents)

		self.first_result_widget = None

		if len(results):

			for result in results:
				comment = urllib2.unquote(result[2])

				icon_name = result[3].replace('/', '-')
				if not self.icon_theme.has_icon(icon_name):
					icon_name = 'text-x-generic'

				button = self.add_launcher_entry(result[0], icon_name, self.search_section_contents, comment = comment)
				button.connect('clicked', self.on_xdg_button_clicked, result[1])

				if self.first_result_widget is None:
					self.first_result_widget = button

			self.search_section_contents.show()
			self.set_section_has_entries(self.search_section_slab)

			if self.selected_section is None or self.selected_section == self.search_section_slab:
				self.search_section_slab.show()
				self.hide_no_results_text()

			else:
				self.consider_showing_no_results_text()

		else:

			self.set_section_is_empty(self.search_section_slab)

			if self.selected_section is None or self.selected_section == self.search_section_slab:
				self.search_section_slab.hide()

			if self.no_results_to_show:
				self.consider_showing_no_results_text()


	def prepare_viewport(self):

		dummy_window = gtk.Window()
		dummy_window.realize()
		scrolledwin_style = dummy_window.get_style().copy()
		scrolledwin_style.bg[gtk.STATE_NORMAL] = scrolledwin_style.base[gtk.STATE_NORMAL]
		self.get_object('ScrolledViewport').set_style(scrolledwin_style)

		# TODO: make sure the viewport color changes on the fly when user changes theme too!


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

		path = self.escape_quotes(path)
		return self.launch_raw("xdg-open '%s'" % path)


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


	def show_no_results_text(self, text = None):

		if text is None: text = _('No results to show')

		self.no_results_label.set_text(text)
		self.no_results_slab.show()


	def hide_no_results_text(self):

		self.no_results_slab.hide()


	def consider_showing_no_results_text(self):

		if self.selected_section is None:
			self.show_no_results_text()
			return 
			
		if self.section_list[self.selected_section]['has-entries']:
			self.selected_section.show()
			self.hide_no_results_text()

		else:
			self.selected_section.hide()
			self.show_no_results_text(_('No results to show in "%s"') % self.section_list[self.selected_section]['title'])


	def disappear_with_section(self, section_slab):

		self.section_list[section_slab]['has-entries'] = False
		self.section_list[section_slab]['category'].hide()
		section_slab.hide()


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


	def escape_quotes(self, str):

		str = re.sub("'", "\\'", str)
		str = re.sub('"', '\\"', str)
		return str


def return_true(*args):
	return True


def applet_factory(applet, iid):
	
	button = gtk.ImageMenuItem(Cardapio.default_panel_label)

	cardapio = Cardapio(hidden = True, panel_button = button, panel_applet = applet)

	button_icon = gtk.image_new_from_icon_name('distributor-logo', gtk.ICON_SIZE_SMALL_TOOLBAR)
	button.set_image(button_icon)

	menu = gtk.MenuBar()
	menu.add(button)

	button.connect('button-press-event', cardapio.on_panel_button_toggled)
	menu.connect('button-press-event', cardapio.on_panel_button_press)

	# make sure menuitem doesn't change focus on mouseout/mousein
	button.connect('enter-notify-event', return_true)
	button.connect('leave-notify-event', return_true)

	applet.connect('change-background', cardapio.on_panel_change_background)
	applet.add(menu)
	applet.show_all()

	return True


