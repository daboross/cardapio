#!/usr/bin/env python

#  
#  Copyright (C) 2010 Thiago Teixeira
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

from sys import exit
import atexit
import gobject
import os
import subprocess

try:
	from signal import signal, SIGTERM
except ImportError, e:
	exit()

def cleanup():
	subprocess.Popen('cardapio docky-uninstall', shell = True)

if __name__ == "__main__":
	subprocess.Popen('cardapio docky-install', shell = True)
	subprocess.Popen('cardapio hidden', shell = True)

	mainloop = gobject.MainLoop(is_running=True)

	atexit.register (cleanup)
	signal(SIGTERM, lambda signum, stack_frame: exit(0))

	mainloop.run()

