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


	# NOTE: This method is cloned in cardapio_helper.py	
	def get_dock_for_this_helper(self):
		"""
		Returns the name of the dock in which it finds the launcher for
		Cardapio. If there's none or there is more than one dock,
		LauncherError is raised.
		"""

		docks_with_cardapio = []

		for dock in self.active_docks:

			dock_launchers = self.gconf_client.get_list(self.docky_iface_gconf_root + dock + '/Launchers', gconf.VALUE_STRING)
			cardapio_launchers = filter(lambda launcher: launcher.endswith(self.cardapio_desktop), dock_launchers)

			# multiple Cardapio launchers on one dock
			if(len(cardapio_launchers) > 1):
				raise LauncherError(True)
			elif len(cardapio_launchers) == 1:
				docks_with_cardapio.append(dock)

		# multiple docks with Cardapio launchers
		if len(docks_with_cardapio) != 1:
			raise LauncherError(len(docks_with_cardapio) > 1)

		return docks_with_cardapio[0]


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


	def get_horizontal_offset(self, dock):
		"""
		Returns the horizontal offset necessary to avoid overlapping of Cardapio launchers'
		tooltip	with Cardapio's window. The offset depends on whether the dock is in panel
		mode.
		"""

		return 10 if self.gconf_client.get_bool(self.docky_iface_gconf_root + dock + '/PanelMode') else 20


	def get_vertical_offset(self, position, dock):
		"""
		Returns the vertical offset necessary to avoid overlapping of Cardapio launchers'
		tooltip	with Cardapio's window. The offset depends on whether the dock is in panel
		mode and on it's position (on top it's lower because the decoration bar pushes
		Cardapio down only when it's near the bottom of the screen).
		"""

		if position == 'Bottom':
			return 55 if self.gconf_client.get_bool(self.docky_iface_gconf_root + dock + '/PanelMode') else 90
		else:
			return 30 if self.gconf_client.get_bool(self.docky_iface_gconf_root + dock + '/PanelMode') else 60


	def get_best_position(self, dock_num):
		"""
		Determines the best (x, y) position for Cardapio in docky-mode.
		Takes things like Docky's orientation, it's size or zoom mode
		into account.
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



# NOTE: This class is cloned in cardapio_helper.py
class LauncherError(Exception):
	"""
	Exception raised when there are none or multiple Cardapio launchers on
	Docky's docks. The "multiple" flag says whether there were many or none.
	"""

	def __init__(self, multiple):
		self.multiple = multiple
