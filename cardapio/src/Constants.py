#
#  Cardapio is an alternative menu applet, launcher, and much more!
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

# These constants used to static members of the Cardapio class. However it turns
# out that loading all of Cardapio just for using these constants (as used to
# happen in the 'cardapio' script) proved quite slow. So this file helps speed
# things up.

APP = 'cardapio'

BUS_NAME_STR = 'org.varal.Cardapio'
BUS_OBJ_STR  = '/org/varal/Cardapio'

DONT_SHOW       = 0
SHOW_CENTERED   = 1
SHOW_NEAR_MOUSE = 2

CORE_PLUGINS = [
		'applications',
		'command_launcher',
		'google',
		'google_localized',
		'pinned',
		'places',
		'software_center',
		'tracker',
		'tracker_fts',
		'zeitgeist_smart',
		'zeitgeist_categorized',
		'zeitgeist_simple',
		]

REQUIRED_PLUGINS = ['pinned']
BUILTIN_PLUGINS = ['applications', 'places', 'pinned']

