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

from misc import *
import sys

try:
	import gtk
	import glib
	import mateapplet
	from CardapioAppletInterface import *

except Exception, exception:
	fatal_error("Fatal error loading Cardapio's applet for the Mate Panel", exception)
	sys.exit(1)


class CardapioMateApplet(CardapioAppletInterface):

	PANEL_SIZE_CHANGE_IGNORE_INTERVAL = 200 # milliseconds
	SETUP_PANEL_BUTTON_DELAY          = 100 # milliseconds (must be smaller than PANEL_SIZE_CHANGE_IGNORE_INTERVAL)

	panel_type = PANEL_TYPE_MATE

	IS_CONFIGURABLE = True
	IS_CONTROLLABLE = True

	# Added this to fix a bug where CardapioMateApplet was being
	# reinstantiated (possibly by Mate Panel) right after it was destroyed! As
	# a hackish fix I make sure CardapioMateApplet is a singleton using the
	# variable below. Eek.
	_singleton_instance = None

	def __init__(self, applet):

		if CardapioMateApplet._singleton_instance is not None:
			return CardapioMateApplet._singleton_instance

		CardapioMateApplet._singleton_instance = self

		self.applet = applet
		self.button = gtk.ImageMenuItem()
		self.applet_press_handler = None
		self.applet_enter_handler = None
		self.applet_leave_handler = None


	def setup(self, cardapio):

		self.icon_helper = cardapio.icon_helper
		self.cardapio = cardapio

		self.context_menu_xml = '''
			<popup name="button3">
				<menuitem name="Item 1" verb="Properties" label="%s" pixtype="stock" pixname="gtk-properties"/>
				<menuitem name="Item 2" verb="Edit" label="%s" pixtype="stock" pixname="gtk-edit"/>
				<separator />
				<menuitem name="Item 3" verb="AboutCardapio" label="%s" pixtype="stock" pixname="gtk-about"/>
				<menuitem name="Item 4" verb="AboutMate" label="%s" pixtype="none"/>
				<menuitem name="Item 5" verb="AboutDistro" label="%s" pixtype="none"/>
			</popup>
			''' % (
				_('_Properties'),
				_('_Edit Menus'),
				_('_About Cardapio'),
				_('_About Mate'),
				_('_About %(distro_name)s') % {'distro_name' : cardapio.distro_name}
			)

		self.context_menu_verbs = [
			('Properties', self.open_options_dialog),
			('Edit', self.launch_edit_app),
			('AboutCardapio', self.open_about_dialog),
			('AboutMate', self.open_about_dialog),
			('AboutDistro', self.open_about_dialog)
		]

		self.button.set_tooltip_text(_('Access applications, folders, system settings, etc.'))
		self.button.set_always_show_image(True)
		self.button.set_name('CardapioApplet')

		menubar = gtk.MenuBar()
		menubar.set_name('CardapioAppletMenu')
		menubar.add(self.button)

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
			widget "*MatePanelApplet" style:highest "cardapio-applet-style"
			''')

		self.applet.add(menubar)

		self.applet.connect('size-allocate', self._on_panel_size_changed)
		self.applet.connect('change-orient', self._panel_change_orientation)
		self.applet.connect('change-background', self._on_panel_change_background)
		self.applet.connect('destroy', self._on_panel_destroy)

		self.applet.set_applet_flags(mateapplet.EXPAND_MINOR)
		self.applet.show_all()

		return True


	def update_from_user_settings(self, settings):

		self.applet_label  = settings['applet label']
		self.applet_icon   = settings['applet icon']
		self.open_on_hover = settings['open on hover']
		self._load_settings()


	def get_size(self):

		# here we get the size of the toplevel window because that's actually
		# just the small area of the panel where the applet will be drawn --
		# *not* the entire panel as you would expect.

		panel = self.button.get_toplevel().window
		wh = panel.get_size()
		return  wh


	def get_position(self):

		xy = self.applet.get_window().get_origin()
		return xy


	def get_orientation(self):

		orientation = self.applet.get_orient()
		if orientation == mateapplet.ORIENT_UP  : return POS_BOTTOM # bottom and top are flipped for some reason
		if orientation == mateapplet.ORIENT_DOWN: return POS_TOP    # bottom and top are flipped for some reason
		if orientation == mateapplet.ORIENT_LEFT: return POS_RIGHT  # left and right are flipped for some reason
		return POS_LEFT # left and right are flipped for some reason


	def draw_toggled_state(self, state):

		if state: self.button.select()
		else: self.button.deselect()


	def _panel_change_orientation(self, *dummy):
		"""
		Resize the panel applet when the panel orientation is changed
		"""

		orientation = self.applet.get_orient()

		if orientation == mateapplet.ORIENT_UP or orientation == mateapplet.ORIENT_DOWN:
			self.button.parent.set_child_pack_direction(gtk.PACK_DIRECTION_LTR)
			self.button.child.set_angle(0)
			self.button.child.set_alignment(0, 0.5)

		elif orientation == mateapplet.ORIENT_RIGHT:
			self.button.parent.set_child_pack_direction(gtk.PACK_DIRECTION_BTT)
			self.button.child.set_angle(90)
			self.button.child.set_alignment(0.5, 0)

		elif orientation == mateapplet.ORIENT_LEFT:
			self.button.parent.set_child_pack_direction(gtk.PACK_DIRECTION_TTB)
			self.button.child.set_angle(270)
			self.button.child.set_alignment(0.5, 0)


	def _on_panel_change_background(self, widget, bg_type, color, pixmap):
		"""
		Update the Cardapio applet background when the user changes
		the panel background
		"""

		self.button.parent.set_style(None)

		clean_style = gtk.RcStyle()
		self.button.parent.modify_style(clean_style)

		if bg_type == mateapplet.COLOR_BACKGROUND:
			self.button.parent.modify_bg(gtk.STATE_NORMAL, color)

		elif bg_type == mateapplet.PIXMAP_BACKGROUND:
			style = self.button.parent.get_style()
			style.bg_pixmap[gtk.STATE_NORMAL] = pixmap
			self.button.parent.set_style(style)

		#elif bg_type == mateapplet.NO_BACKGROUND: pass


	def _on_panel_size_change_done(self):
		"""
		Restore a signal handler that we had deactivated
		"""

		self.applet.handler_unblock_by_func(self._on_panel_size_changed)
		return False # must return false to cancel the timer


	def _on_panel_size_changed(self, widget, allocation):
		"""
		Resize the panel applet when the panel size is changed
		"""

		self.applet.handler_block_by_func(self._on_panel_size_changed)
		glib.timeout_add(CardapioMateApplet.SETUP_PANEL_BUTTON_DELAY, self._load_settings)
		glib.timeout_add(CardapioMateApplet.PANEL_SIZE_CHANGE_IGNORE_INTERVAL, self._on_panel_size_change_done) # added this to avoid an infinite loop


	def _on_panel_button_pressed(self, widget, event):
		"""
		Show the context menu when the user right-clicks the panel applet
		"""

		if event.type == gtk.gdk.BUTTON_PRESS:

			if event.button == 3:

				widget.emit_stop_by_name('button-press-event')
				self.applet.setup_menu(self.context_menu_xml, self.context_menu_verbs, None)

			if event.button == 2:

				# make sure middle click does nothing, so it can be used to move
				# the applet

				widget.emit_stop_by_name('button-press-event')
				self.cardapio.hide()


	def _on_panel_button_toggled(self, widget, event, ignore_main_button):
		"""
		Show/Hide cardapio when the panel applet is clicked
		"""

		if event.type == gtk.gdk.BUTTON_PRESS:

			if event.button == 1:

				if not ignore_main_button:
					self.cardapio.show_hide()

				return True # required! or we get strange focus problems


	def _on_applet_cursor_enter(self, widget, event):
		"""
		Handler for when the cursor enters the panel applet.
		"""

		self.cardapio.show_hide()
		return True


	def _on_applet_cursor_leave(self, *dummy):
		"""
		Handler for whent the cursor leaves the panel applet.
		"""

		self.cardapio.handle_mainwindow_cursor_leave()


	def _on_panel_destroy(self, *dummy):
		"""
		Handler for when the applet is removed from the panel
		"""

		self.cardapio.save_and_quit()


	def _load_settings(self):

		self.button.set_label(self.applet_label)

		if self.applet_icon:
			button_icon_pixbuf = self.icon_helper.get_icon_pixbuf(self.applet_icon, self._get_best_icon_size_for_panel(), 'start-here')
			button_icon = gtk.image_new_from_pixbuf(button_icon_pixbuf)
			self.button.set_image(button_icon)
		else:
			self.button.set_image(None)

		clean_imagemenuitem = gtk.ImageMenuItem()
		is_horizontal = (self.applet.get_orient() in (mateapplet.ORIENT_UP, mateapplet.ORIENT_DOWN))

		if self.applet_label and self.applet_icon:
			toggle_spacing = clean_imagemenuitem.style_get_property('toggle-spacing')
		else:
			toggle_spacing = 0

		if is_horizontal:
			horizontal_padding = clean_imagemenuitem.style_get_property('horizontal-padding')
		else:
			horizontal_padding = 0

		gtk.rc_parse_string('''
			style "cardapio-applet-style"
			{
				GtkImageMenuItem::toggle-spacing = %d
				GtkImageMenuItem::horizontal-padding = %d
			}
			widget "*CardapioApplet" style:application "cardapio-applet-style"
			''' % (toggle_spacing, horizontal_padding))

		# apparently this happens sometimes (maybe when the parent isn't realized yet?)
		if self.button.parent is None: return

		menubar = self.button.parent 
		menubar.remove(self.button)
		menubar.add(self.button)

		menubar.connect('button-press-event', self._on_panel_button_pressed)

		if self.applet_press_handler is not None:
			try:
				self.button.disconnect(self.applet_press_handler)
				self.button.disconnect(self.applet_enter_handler)
				self.button.disconnect(self.applet_leave_handler)
			except: pass

		if self.open_on_hover:
			self.applet_press_handler = self.button.connect('button-press-event', self._on_panel_button_toggled, True)
			self.applet_enter_handler = self.button.connect('enter-notify-event', self._on_applet_cursor_enter)
			self.applet_leave_handler = self.button.connect('leave-notify-event', self._on_applet_cursor_leave)

		else:
			self.applet_press_handler = self.button.connect('button-press-event', self._on_panel_button_toggled, False)
			self.applet_enter_handler = self.button.connect('enter-notify-event', return_true)
			self.applet_leave_handler = self.button.connect('leave-notify-event', return_true)


	def _get_best_icon_size_for_panel(self):
		"""
		Returns the best icon size for the current panel size
		"""

		try:
			panel_width, panel_height = self.get_size()
		except:
			return gtk.icon_size_lookup(gtk.ICON_SIZE_LARGE_TOOLBAR)[0]

		orientation = self.applet.get_orient()

		if orientation in (mateapplet.ORIENT_DOWN, mateapplet.ORIENT_UP):
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


	def open_about_dialog(self, widget, verb):
		"""
		This method simply forwards its "verb" argument to the appropriate
		method in Cardapio, acting as a layer to remove the dependence on the
		"widget" argument.
		"""
		self.cardapio.handle_about_menu_item_clicked(verb)


	def open_options_dialog(self, widget, verb):
		self.cardapio.open_options_dialog()


	def launch_edit_app(self, widget, verb):
		self.cardapio.handle_editor_menu_item_clicked()


	def get_screen_number(self):
		"""
		Returns the number of the screen where the applet is placed
		"""
		screen = self.button.get_screen()
		if screen is None: return 0
		return screen.get_number()


