import gconf
import gtk

class DockySettingsHelper:
	"""
	Helper class for dealing with Docky's GConf settings.
	"""

	# GConf keys of Docky's settings
	docky_gconf_root = '/apps/docky-2/Docky'
	docky_dcontroller_gconf_root = docky_gconf_root + '/DockController/'
	docky_iface_gconf_root = docky_gconf_root + '/Interface/DockPreferences/'

	# name of Cardapio's launcher
	cardapio_desktop = 'cardapio.desktop'

	gconf_client = gconf.client_get_default()


	def __init__(self):
		# sets the names of user's active docks
		self.active_docks = self.gconf_client.get_list(self.docky_dcontroller_gconf_root + 'ActiveDocks', gconf.VALUE_STRING)


	def get_main_dock(self):
		"""
		Returns the name of the main Docky's dock (the one that keeps the
		unknown launchers). If there's none, raises MainDockError and if
		there are more, returns the first one's name.
		"""

		main_docks = filter(lambda dock:
			self.gconf_client.get_bool(self.docky_iface_gconf_root + dock + '/WindowManager'),
		self.active_docks)

		if len(main_docks) == 0:
			raise MainDockError

		return main_docks[0]


	def get_icon_size(self, dock):
		"""
		Returns the IconSize property for chosen dock.
		"""

		return self.gconf_client.get_int(self.docky_iface_gconf_root + dock + '/IconSize')


	def get_zoom_percentage(self, dock):
		"""
		Returns the ZoomPercent property for chosen dock if zoom is
		enabled (ZoomEnabled). If not, returns neutral scaling
		factor (number 1).
		"""

		if(self.gconf_client.get_bool(self.docky_iface_gconf_root + dock + '/ZoomEnabled')):
			return self.gconf_client.get_float(self.docky_iface_gconf_root + dock + '/ZoomPercent')
		else:
			return 1


	def get_position(self, dock):
		"""
		Returns the Position property for chosen dock.
		"""

		return self.gconf_client.get_string(self.docky_iface_gconf_root + dock + '/Position')


	def is_in_panel_mode(self, dock):
		"""
		Returns a flag saying whether the given dock is in panel mode.
		"""

		return self.gconf_client.get_bool(self.docky_iface_gconf_root + dock + '/PanelMode')


	def is_showing_hover(self):
		"""
		Returns a flag saying whether Docky's icon has a hover.
		"""

		return self.gconf_client.get_string(self.docky_gconf_root + '/Items/DockyItem/HoverText') != ''


	def get_horizontal_offset(self, dock):
		"""
		Returns the horizontal offset necessary to avoid overlapping of Cardapio launchers'
		tooltip	with Cardapio's window. The offset depends on whether the dock is in panel
		mode.
		"""

		return 20 if self.is_in_panel_mode(dock) else 30


	def get_vertical_offset(self, dock, position, is_decorated):
		"""
		Returns the vertical offset necessary to avoid overlapping of Cardapio launchers'
		tooltip	with Cardapio's window. The offset depends on whether the dock is in panel
		mode, whether the icon of Docky has a hover and whether Cardapio is decorated.
		"""

		# initial offset
		offset = 12 if self.is_in_panel_mode(dock) else 35

		# higher if the launcher's on the bottom dock and Cardapio's decorated
		if position == 'Bottom' and is_decorated:
			offset += 25

		# higher if Docky's icon has a hover
		if self.is_showing_hover():
			offset += 30

		return offset


	def get_best_position(self, dock_num, is_decorated):
		"""
		Determines the best (x, y) position for Cardapio in docky-mode.
		Takes things like Docky's orientation, it's size or zoom mode
		into account. Also, requires a parameter saying whether Cardapio's
		window is decorated.
		"""

		# properties of our dock
		icon_size = self.get_icon_size(dock_num)
		zoom_percent = self.get_zoom_percentage(dock_num)
		position = self.get_position(dock_num)

		# mouse position and screen size
		mouse_x, mouse_y, dummy = gtk.gdk.get_default_root_window().get_pointer()
		screen_width, screen_height = gtk.gdk.screen_width(), gtk.gdk.screen_height()

		# offsets from screen's borders
		horizontal_offset = self.get_horizontal_offset(dock_num)
		vertical_offset = self.get_vertical_offset(dock_num, position, is_decorated)

		# calculating final position...
		if position == 'Bottom':
			x = mouse_x
			y = screen_height - (icon_size * zoom_percent + vertical_offset)
		elif position == 'Top':
			x = mouse_x
			y = icon_size * zoom_percent + vertical_offset
		elif position == 'Left':
			x = icon_size * zoom_percent + horizontal_offset
			y = mouse_y
		elif position == 'Right':
			x = screen_width - (icon_size * zoom_percent + horizontal_offset)
			y = mouse_y

		return x, y



class MainDockError(Exception):
	"""
	Exception raised when the DockySettingsHelper is unable to find the
	main dock of Docky.
	"""

	pass
