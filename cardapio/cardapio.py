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

import os
import re
import sys
import gtk
import glib
import gmenu
import locale
import gobject
import urllib2
import gettext
import commands
import subprocess
import gnomeapplet
import dbus, dbus.service
from xdg import BaseDirectory, DesktopEntry
from dbus.mainloop.glib import DBusGMainLoop

APP = 'Cardapio'
DIR = 'locale'

locale.setlocale(locale.LC_ALL, '')
gettext.bindtextdomain(APP, DIR)
gettext.textdomain(APP)
_ = gettext.gettext

# TODO: add "No results to show" text
# TODO: fix tabbing of first_app_widget / first_result_widget  
# TODO: make cardapio window open near panel applet
# TODO: make cardapio applet a menuitem, so we can use the top-left pixel
# TODO: add "places" to cardapio
# TODO: add icons for System, Session, and All categories

class Cardapio(dbus.service.Object):

	FOLDERS = 1
	ITEMS   = 2
	BOTH    = 3

	bus_name_str = 'org.varal.Cardapio'
	bus_obj_str  = '/org/varal/Cardapio'

	menu_rebuild_delay       = 2
	min_search_string_length = 3
	search_results_limit     = 15
	search_update_msec       = 100

	def __init__(self, hidden = False, toggle_button = None):

		self.panel_button = toggle_button
		self.auto_toggled_panel_button = False
		self.auto_toggled_sidebar_button = False

		# TODO: remember position and dimensions between sessions. Use gconf? What?
		self.window_position = (0, 0)
		self.window_size = None

		self.app_list = []
		self.section_list = {}
		self.shown_section = None

		self.first_app_widget = None
		self.first_result_widget = None
		self.visible = False

		self.app_tree = gmenu.lookup_tree('applications.menu')
		self.sys_tree = gmenu.lookup_tree('settings.menu')

		# TODO: internationalize these
		self.exec_pattern = re.compile("^(.*?)\s+\%[a-zA-Z]$")
		self.sanitize_query_pattern = re.compile("[^a-zA-Z0-9]")

		self.set_up_dbus()
		self.set_up_tracker_search()
		self.build_ui()
		self.first_app_widget = self.app_list[0][1]

		self.app_tree.add_monitor(self.on_menu_data_changed)
		self.sys_tree.add_monitor(self.on_menu_data_changed)

		if not hidden: self.show()


	def set_up_dbus(self):

		DBusGMainLoop(set_as_default=True)
		self.bus = dbus.SessionBus()
		dbus.service.Object.__init__(self, self.bus, Cardapio.bus_obj_str)


	def set_up_tracker_search(self):

		self.tracker_object = None
		self.search_timer = None

		if self.bus.request_name('org.freedesktop.Tracker1') == dbus.bus.REQUEST_NAME_REPLY_IN_QUEUE:
			self.tracker_object = self.bus.get_object('org.freedesktop.Tracker1', '/org/freedesktop/Tracker1/Resources')


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

		if self.shown_section is None:
			self.clear_search_entry()
		else:
			self.show_all_nonempty_sections()

		self.auto_toggled_sidebar_button = True
		widget.set_active(False)


	def on_sidebar_button_clicked(self, widget, section_slab):

		if self.auto_toggled_sidebar_button:
			self.auto_toggled_sidebar_button = False
			return True

		if self.shown_section == section_slab:
			self.shown_section = None # necessary!
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

		self.prepare_viewport()

		self.rebuild_all()

		# make sure buttons have icons!
		settings = gtk.settings_get_default()
		settings.set_property('gtk-button-images', True)

		self.window.set_keep_above(True)


	def set_focus_handler(self):

		# TODO: why does autohive misbehave when not running in panel mode?
		#self.window.connect_after('focus_out_event', self.on_mainwindow_focus_out)
		pass


	def on_mainwindow_destroy(self, widget, *etc, **kwetc):

		gtk.main_quit()


	def on_mainwindow_delete_event(self, widget, *etc, **kwetc):

		if self.panel_button:
			# keep window alive is in panel mode
			#widget.emit_stop_by_name('destroy')
			return True


	def on_mainwindow_focus_out(self, widget, *etc, **kwetc):

		if self.panel_button is not None:
			self.hide()


	def on_mainwindow_configure_event(self, widget, *etc, **kwetc):

		self.save_dimensions()


	def on_icon_theme_changed(self, icon_theme):

		glib.timeout_add_seconds(Cardapio.menu_rebuild_delay, self.rebuild_all)


	def on_menu_data_changed(self, *etc):

		glib.timeout_add_seconds(Cardapio.menu_rebuild_delay, self.rebuild_all)


	def on_searchentry_icon_press(self, widget, *etc, **kwetc):

		self.clear_search_entry()


	def on_searchentry_changed(self, widget, *etc, **kwetc):

		text = self.search_entry.get_text().strip()

		self.search_menus(text)

		if len(text) == 0:
			self.disappear_with_section(self.system_section_slab)
			self.disappear_with_section(self.session_section_slab)
			self.disappear_with_section(self.search_section_slab)

		if self.tracker_object is not None:
			if len(text) >= Cardapio.min_search_string_length:
				self.schedule_search_with_tracker(text)
			else:
				self.search_section_slab.hide()


	def search_menus(self, text):

		self.first_app_widget = None

		for sec in self.section_list:
			self.section_is_empty(sec)
			#DEL self.section_list[sec]['has_entries'] = False
		
		for app in self.app_list:
			if app[0].find(text) == -1:
				app[1].hide()
			else:
				app[1].show()
				self.section_has_entries(app[2])
				#DEL self.section_list[app[2]]['has_entries'] = True
				if self.first_app_widget is None:
					self.first_app_widget = app[1]

		if self.shown_section is None:
			self.show_all_nonempty_sections()


	def schedule_search_with_tracker(self, text):

		if self.search_timer is not None:
			gobject.source_remove(self.search_timer)

		self.search_timer = gobject.timeout_add(Cardapio.search_update_msec, self.search_with_tracker, text)


	def search_with_tracker(self, text):

		gobject.source_remove(self.search_timer)

		# no .lower(), since there's no fn:lower-case in tracker
		#text = self.escape_quotes(text).lower()
		text = self.escape_quotes(text)

		self.tracker_object.SparqlQuery(
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
		#       FILTER (fn:contains(fn:lower-case(?title, '%s')))
		#
		# - fts:match does not match source code! so not good for searching
		# files in general, only documents.
		#
		# - regex works, but it's too slow for normal use...


	def is_searchfield_empty(self):

		return (len(self.search_entry.get_text().strip()) == 0)


	def on_searchentry_activate(self, widget, *etc, **kwetc):

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


	def on_searchentry_key_press_event(self, widget, event, *etc, **kwetc):

		# make Tab go to first result element
		if event.keyval == gtk.gdk.keyval_from_name('Tab'):

			if self.first_app_widget is not None:
				self.first_app_widget.connect('key-press-event', self.on_first_button_key_press_event)
				self.window.set_focus(self.first_app_widget)

			elif self.first_result_widget is not None:
				self.first_result_widget.connect('key-press-event', self.on_first_button_key_press_event)
				self.window.set_focus(self.first_result_widget)

		elif event.keyval == gtk.gdk.keyval_from_name('Escape'):

			if self.is_searchfield_empty():
				self.hide()

			self.clear_search_entry()

		else: return False
		return True


	def on_mainwindow_key_press_event(self, widget, event, *etc, **kwetc):

		if self.search_entry.is_focus(): return False

		if event.keyval == gtk.gdk.keyval_from_name('Escape'):

			self.clear_search_entry()
			self.window.set_focus(self.search_entry)

		else: return False
		return True


	# make Tab go from first result element to text entry widget
	def on_first_button_key_press_event(self, widget, event, *etc, **kwetc):

		if event.keyval == gtk.gdk.keyval_from_name('ISO_Left_Tab'):

			self.window.set_focus(self.search_entry)

		else: return False
		return True


	def restore_dimensions(self):

		if self.window_position is not None: 
			self.window.move(*self.window_position)

		if self.window_size is not None: 
			self.window.resize(*self.window_size)


	def save_dimensions(self):

		self.window_position = self.window.get_position()
		self.window_size = self.window.get_size()


	def show(self, do_auto_toggle = True):

		self.visible = True

		if self.window_position is None:
			self.save_dimensions()
		else:
			self.restore_dimensions()

		self.window.set_focus(self.search_entry)
		self.set_focus_handler()

		if do_auto_toggle:
			self.auto_toggle_button(True)

		self.window.show()


	def hide(self, do_auto_toggle = True):

		if do_auto_toggle:
			self.auto_toggle_button(False)

		self.window.hide()

		self.visible = False
		self.clear_search_entry()
		self.show_all_nonempty_sections()


	@dbus.service.method(dbus_interface=bus_name_str, in_signature=None, out_signature=None)
	def show_hide(self):

		if self.visible: self.hide()
		else: self.show()


	def on_panel_button_clicked(self, widget):

		if self.auto_toggled_panel_button:
			self.auto_toggled_panel_button = False
			return True

		if self.visible: self.hide(do_auto_toggle = False)
		else: self.show(do_auto_toggle = False)


	def auto_toggle_button(self, state):

		if self.panel_button is not None:
			self.auto_toggled_panel_button = True
			self.panel_button.set_active(state)


	def rebuild_all(self):

		self.clear_application_pane()
		self.clear_category_pane()
		self.clear_system_pane()
		self.build_places_list()
		self.build_application_list()

		self.add_hidden_session_slab()
		self.add_hidden_system_slab()
		self.add_hidden_search_results_slab()


	def build_places_list(self):

		# TODO: make a category called "places", and treat it like any other
		# app category...
		pass


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


	def build_application_list(self):

		self.section_list = {}
		self.app_list = []

		button = self.add_sidebar_button(_('All'), None, self.category_pane, comment = _('Show all categories'))
		button.connect('clicked', self.on_all_sections_sidebar_button_clicked)
		self.all_sections_sidebar_button = button 

		for node in self.app_tree.root.contents:

			if isinstance(node, gmenu.Directory):

				# add to main pane
				self.add_section_slab(node)

			elif isinstance(node, gmenu.Entry):

				# add to system pane
				button = self.add_sidebar_button(node.name, node.icon, self.system_pane, comment = node.get_comment(), use_toggle_button = False)
				button.connect('clicked', self.launch_app, node.desktop_file_path)


	def add_section_slab(self, node):

		# add category to category pane
		sidebar_button = self.add_sidebar_button(node.name, node.icon, self.category_pane, comment = node.get_comment())

		# add category to application pane
		section_slab, section_contents = self.add_application_section(node.name)

		# add all apps in this category to application pane
		self.add_tree_to_app_list(node, section_contents)

		sidebar_button.connect('clicked', self.on_sidebar_button_clicked, section_slab)
		self.section_list[section_slab] = {'has_entries': True, 'category': sidebar_button}


	def add_hidden_slab(self, title_str, icon_name = None, comment = ''):

		# add category to category pane
		sidebar_button = self.add_sidebar_button(title_str, icon_name, self.category_pane, comment = comment)

		# add category to application pane
		section_slab, section_contents = self.add_application_section(title_str)

		sidebar_button.connect('clicked', self.on_sidebar_button_clicked, section_slab)

		sidebar_button.hide()
		section_slab.hide()
		self.section_list[section_slab] = {'has_entries': False, 'category': sidebar_button}

		return section_slab, section_contents


	def add_hidden_system_slab(self):

		section_slab, section_contents = self.add_hidden_slab(_('System Tasks'))

		self.add_tree_to_app_list(self.app_tree.root, section_contents, recursive = False)
		self.add_tree_to_app_list(self.sys_tree.root, section_contents)

		self.system_section_slab = section_slab


	def add_hidden_session_slab(self):

		section_slab, section_contents = self.add_hidden_slab(_('Session Tasks'))
		self.session_section_slab = section_slab
		self.session_section_contents = section_contents
		self.build_session_list()


	def add_hidden_search_results_slab(self):

		# add system category to application pane
		section_slab, section_contents = self.add_hidden_slab(_('Other Results'))
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
			app_list.append([button_str.lower(), button, parent_widget.parent.parent])
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

		section_slab.set_name(section_slab.name + s)
		section_contents.set_name(section_contents.name + s + c)

		self.application_pane.pack_start(section_slab, expand = False, fill = False)

		return section_slab, section_contents


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
				button.connect('clicked', self.launch_app, node.desktop_file_path)

			elif isinstance(node, gmenu.Directory) and recursive:

				self.add_tree_to_app_list(node, parent_widget)


	def handle_search_error(self, error):

		print error
		pass


	def handle_search_result(self, results):

		container = self.search_section_contents.parent
		container.remove(self.search_section_contents)
		self.search_section_contents = gtk.VBox()
		container.add(self.search_section_contents)

		if len(results):

			self.first_result_widget = None

			for result in results:
				comment = urllib2.unquote(result[2])

				icon_name = result[3].replace('/', '-')
				if not self.icon_theme.has_icon(icon_name):
					icon_name = 'text-x-generic'

				button = self.add_launcher_entry(result[0], icon_name, self.search_section_contents, comment = comment)
				button.connect('clicked', lambda x, y: self.launch_xdg(y), result[1])

				if self.first_result_widget is None:
					self.first_result_widget = button

			self.search_section_contents.show()
			self.section_has_entries(self.search_section_slab)
			#DEL self.section_list[self.search_section_slab]['has_entries'] = True

			if self.shown_section is None or self.shown_section == self.search_section_slab:
				self.search_section_slab.show()

		else:

			self.section_is_empty(self.search_section_slab)
			#DEL self.section_list[self.search_section_slab]['has_entries'] = False

			if self.shown_section is None or self.shown_section == self.search_section_slab:
				self.search_section_slab.hide()


	def prepare_viewport(self):

		dummy_window = gtk.Window()
		dummy_window.realize()
		scrolledwin_style = dummy_window.get_style().copy()
		scrolledwin_style.bg[gtk.STATE_NORMAL] = scrolledwin_style.base[gtk.STATE_NORMAL]
		self.get_object('ScrolledViewport').set_style(scrolledwin_style)

		# TODO: make sure the viewport color changes on the fly when user changes theme too!


	def launch_app(self, widget, desktop_path):

		if os.path.exists(desktop_path):

			path = DesktopEntry.DesktopEntry(desktop_path).getExec()

			# Strip last part of path if it contains %<a-Z>
			match = self.exec_pattern.match(path)

			if match is not None:
				path = match.group(1)

			self.launch_raw(path)


	def launch_xdg(self, path):

		path = self.escape_quotes(path)
		self.launch_raw("xdg-open '%s'" % path)


	def launch_raw(self, path):

		try:
			subprocess.Popen(path, shell=True)

		except OSError:
			pass

		self.hide()


	def show_all_nonempty_sections(self):

		for sec in self.section_list:
			if self.section_list[sec]['has_entries']:
				sec.show()
			else:
				sec.hide()

		if self.shown_section is not None:
			self.auto_toggled_sidebar_button = True
			self.section_list[self.shown_section]['category'].set_active(False)

		self.shown_section = None


	def show_lone_section(self, section_slab):

		for sec in self.section_list:
			sec.hide()

		if self.shown_section is not None:
			self.auto_toggled_sidebar_button = True
			self.section_list[self.shown_section]['category'].set_active(False)

		self.all_sections_sidebar_button.set_sensitive(True)
		self.shown_section = section_slab
		section_slab.show()


	def disappear_with_section(self, section_slab):

		self.section_list[section_slab]['has_entries'] = False
		self.section_list[section_slab]['category'].hide()
		section_slab.hide()


	def section_has_entries(self, section_slab):

		self.section_list[section_slab]['has_entries'] = True
		self.section_list[section_slab]['category'].show()


	def section_is_empty(self, section_slab):

		self.section_list[section_slab]['has_entries'] = False
		self.section_list[section_slab]['category'].hide()


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


