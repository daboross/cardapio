#
#    Cardapio is an alternative Gnome menu applet, launcher, and much more!
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

def fatal_error(title, errortext):
	"""
	This shows a last-resort error message, which does not depend on any
	external modules. It only depends on Tkinter, which is part of Python's
	standard library (although apparently not on Debian systems!)
	"""
	import Tkinter

	label = Tkinter.Label(text = title, padx = 5, pady = 5, anchor = Tkinter.W, justify = Tkinter.LEFT)
	label.pack()

	text = Tkinter.Text(padx = 5, pady = 5, relief=Tkinter.FLAT, wrap=Tkinter.CHAR)
	text.insert(Tkinter.INSERT, errortext, 'code')
	text.pack()

	Tkinter.mainloop()


def which(filename):
	"""
	Searches the folders in the OS's PATH variable, looking for a file called
	"filename". If found, returns the full path. Otherwise, returns None.
	"""
	import os

	for path in os.environ["PATH"].split(os.pathsep):
		if os.access(os.path.join(path, filename), os.X_OK):
			return "%s/%s" % (path, filename)
	return None


def getoutput(shell_command):
	"""
	Returns the output (from stdout) of a shell command. If an error occurs,
	returns False.
	"""
	import commands
	import logging

	try: 
		return commands.getoutput(shell_command)
		#return subprocess.check_output(shell_command, shell = True) # use this line with Python 2.7
	except Exception, exception: 
		logging.info('Exception when executing' + shell_command)
		logging.info(exception)
		return False


def return_true(*dummy): return True
def return_false(*dummy): return False



try:
	import re
	import os
	import gtk
	import gio
	from xdg import BaseDirectory

except Exception, exception:
	fatal_error('Fatal error loading Cardapio libraries', exception)
	sys.exit(1)

class IconHelper:

	def __init__(self):

		self.icon_extension_types = re.compile('.*\.(png|xpm|svg)$')
		self.icon_theme = gtk.icon_theme_get_default()

		self.icon_size_app = gtk.icon_size_lookup(gtk.ICON_SIZE_LARGE_TOOLBAR)[0]
		self.icon_size_category = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)[0]
		self.icon_size_menu = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)[0]

		uninstalled_icon_path = '/usr/share/app-install/icons/'
		if os.path.exists(uninstalled_icon_path):
			self.icon_theme.append_search_path(uninstalled_icon_path)

		self._listener = return_true
		self.icon_theme.connect('changed', self._on_icon_theme_changed)


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


	def register_icon_theme_listener(self, listener):
		"""
		Registed a function to be called when we detect that the icon theme has
		changed
		"""
		self._listener = listener


	def _on_icon_theme_changed(self, icon_theme):
		"""
		Rebuild the Cardapio UI whenever the icon theme changes
		"""

		self._listener()


