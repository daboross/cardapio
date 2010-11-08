import gconf
import gtk

class DockySettingsHelper:
	"""
	Parser of Docky's GConf settings.
	"""

	# GConf root of Docky's settings
	docky_gconf_root = '/apps/docky-2/Docky/Interface/DockPreferences/'
	# list of docks available in settings (Dock1 - Dock6)
	docks = map(lambda x: 'Dock' + str(x), range(1, 7))

	# name of Cardapio's launcher
	cardapio_desktop = 'cardapio.desktop'

	gconf_client = gconf.client_get_default()

	def get_dock_for_this_helper(self):
		"""
		Returns the name of the dock in which it finds the launcher for
		Cardapio. If there's none, returns empty string. If there is
		more than one dock, LookupError is raised.
		"""

		found = None

		for dock in self.docks:
			launchers = self.gconf_client.get_list(self.docky_gconf_root + dock + '/Launchers', 1)
			for launcher in launchers:
				if launcher.endswith(self.cardapio_desktop):
					if found is not None:
						raise LookupError
					else:
						found = dock
						break

		return found


	def get_icon_size(self, dock):
		"""
		Returns the IconSize property for chosen dock.
		"""

		return self.gconf_client.get_int(self.docky_gconf_root + dock + '/IconSize')


	def get_zoom_percentage(self, dock):
		"""
		Returns the ZoomPercent property for chosen dock if zoom is
		enabled (ZoomEnabled). If not, returns neutral scaling
		factor (number 1).
		"""

		if(self.gconf_client.get_bool(self.docky_gconf_root + dock + '/ZoomEnabled')):
			return self.gconf_client.get_float(self.docky_gconf_root + dock + '/ZoomPercent')
		else:
			return 1


	def get_position(self, dock):
		"""
		Returns the Position property for chosen dock.
		"""

		return self.gconf_client.get_string(self.docky_gconf_root + dock + '/Position')


	def get_horizontal_offset(self, dock):
		"""
		Returns the horizontal offset necessary to avoid overlapping of Cardapio launchers'
		tooltip	with Cardapio's window. The offset depends on whether the dock is in panel
		mode.
		"""

		return 10 if self.gconf_client.get_bool(self.docky_gconf_root + dock + '/PanelMode') else 20


	def get_vertical_offset(self, position, dock):
		"""
		Returns the vertical offset necessary to avoid overlapping of Cardapio launchers'
		tooltip	with Cardapio's window. The offset depends on whether the dock is in panel
		mode and on it's position (on top it's lower because the decoration bar pushes
		Cardapio down only when it's near the bottom of the screen).
		"""

		if position == 'Bottom':
			return 55 if self.gconf_client.get_bool(self.docky_gconf_root + dock + '/PanelMode') else 90
		else:
			return 30 if self.gconf_client.get_bool(self.docky_gconf_root + dock + '/PanelMode') else 60


	def get_best_position(self, dock_num):

		# properties of our dock
		icon_size = self.get_icon_size(dock_num)
		zoom_percent = self.get_zoom_percentage(dock_num)
		position = self.get_position(dock_num)

		# mouse position and screen size
		mouse_x, mouse_y, dummy = gtk.gdk.get_default_root_window().get_pointer()
		screen_width, screen_height = gtk.gdk.screen_width(), gtk.gdk.screen_height()

		# offsets from screen's borders
		horizontal_offset = self.get_horizontal_offset(dock_num)
		vertical_offset = self.get_vertical_offset(position, dock_num)

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


