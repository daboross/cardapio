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
	import gi
	from gi.repository import Gtk
	from gi.repository import PanelApplet

	''' PyGTK compatability? :)
	import gi.pygtkcompat

	gi.pygtkcompat.enable() 
	gi.pygtkcompat.enable_gtk(version='3.0')

	import gtk
	'''

	import dbus
	import dbus.service
	from dbus.mainloop.glib import DBusGMainLoop

except Exception, exception:
	fatal_error("Fatal error loading Cardapio's applet for the Gnome Panel", exception)
	sys.exit(1)

class CardapioGnomeApplet():
   popupmenu_xml = """<menuitem name='Preferences' action='Preferences' />"""

   ''' Create a new CardapioApplet instance '''
   def __init__(self,applet):
	self.applet = applet
	self.button = Gtk.ToggleButton()
	self.button.set_relief(Gtk.ReliefStyle.NONE)
	self.button.set_label("Menu")

	self.changing = False

	try:
		# use SolusOS logo by default
		image =  Gtk.Image()
		image.set_from_file("/usr/share/pixmaps/SolusOS.png")
		self.button.set_property("image", image)
	except:
		pass

	self.applet.set_background_widget(self.button)
	self.applet.add(self.button)

	# create dbus connection
	bus = dbus.SessionBus()
	cardapio = bus.get_object("org.varal.Cardapio", "/org/varal/Cardapio")

	self.cardapio = cardapio

	self.is_cardapio_visible = cardapio.get_dbus_method("is_visible")
 
	## The show_hide method :)
	self.button.connect("clicked", self.show_near_point)


	# if you have no handle you need to capture the button-press-event and re-emit it
	# this makes sure the context menu works
	self.button.connect("button-press-event", self.click_handler)

	# dbus call to "cardapio options"
	show_prefs = cardapio.get_dbus_method("open_options_dialog")

	def visibility_toggled(data=None):
		# if cardapio hides, button = not toggled. etc.
		visibility = self.is_cardapio_visible()
		self.button.set_active(visibility)
	cardapio.connect_to_signal("on_menu_visibility_changed", visibility_toggled)

	''' loaded! set 'er up! '''
	def we_loaded(data=None):
		preferences = self.get_preferences()
		self.button.set_label(preferences[0])
		self.set_applet_icon(preferences[1])
	# when cardapio is loaded, set ourselves up accordingly
	cardapio.connect_to_signal("on_cardapio_loaded", we_loaded)

	# show hide method
	self.show_hide = cardapio.get_dbus_method("show_hide_near_point")

	# quit method
	self.quitty = cardapio.get_dbus_method("quit")

	# setup the menu
	# action group
	group = Gtk.ActionGroup("cardapio_actions")

	# preferences item
	a_prefs = Gtk.Action("Preferences", None, "Open the Cardapio preferences dialog", Gtk.STOCK_PREFERENCES)
	a_prefs.connect("activate", lambda x: show_prefs())

	group.add_action(a_prefs)

	# create the menu
	self.applet.setup_menu(self.popupmenu_xml, group)

	# If you want a "handle" use this :)
	#applet.set_flags(PanelApplet.AppletFlags.HAS_HANDLE)
	applet.set_flags(PanelApplet.AppletFlags.EXPAND_MINOR)

	## hook up a preferences method
	self.get_preferences = cardapio.get_dbus_method("get_applet_configuration")

	self.applet.show_all()

	self.applet.connect("destroy", self.shutusdown)

   ''' Set the applets icon '''
   def set_applet_icon(self,icon):
	if "." in icon:
		# tis a filename!
		image = Gtk.Image()
		try:
			image.set_from_file(icon)
			self.button.set_property("image", image)
		except:
			pass
	else:
		# icon theme.
		image = Gtk.Image()
		try:
			if icon == "start-here":
				# use SolusOS logo where possible.
				image.set_from_file("/usr/share/pixmaps/cardapio-dark24.png")
			else:
				image.set_from_icon_name(icon, Gtk.IconSize.BUTTON)
			self.button.set_property("image", image)
		except:
			pass

   ''' we needa quita. '''
   def shutusdown(self, wid, data=None):
	self.quitty()
	Gtk.main_quit()

   def click_handler(self, widg, event):
	if event.button == 3:
		# ignore right clicks, so the applet has a context menu
		widg.emit_stop_by_name('button-press-event')
	return False

   def show_near_point(self, w,data=None):
	# find out where we are on screen ^^
	window = self.applet.get_window()
	xy = window.get_origin()
	x_point = xy[1]
	y_point = xy[2]
	self.show_hide(x_point,y_point)

''' Entry point '''
def CardapioGnomeAppletFactory(applet, iid, data = None):
	DBusGMainLoop(set_as_default=True)
	the_applet = CardapioGnomeApplet(applet)
	return True
