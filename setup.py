from distutils.core import setup
import os

package_data = ['ui/cardapio.ui', 'ui/options.ui']

data_files = [('lib/bonobo/servers', ['src/gnomepanel/cardapio.server'])]

for root, dir, files in os.walk('locale'):
	for file_ in files:
		if len(file_) > 3 and file_.endswith('.mo'):
			data_files.append( (os.path.join('share', root), [os.path.join(root, file_)]) )

for root, dir, files in os.walk('src/plugins'):
	for file_ in files:
		if len(file_) > 3 and file_.endswith('.py'):
			package_data.append(os.path.join(root.replace('src' + os.path.sep, ''), file_))

setup(
	name         = 'Cardapio',
	version      = '0.9.194',
	description  = 'A menu with search capabilities.',
	author       = 'Cardapio Team',
	author_email = 'tvst@hotmail.com',
	url          = 'https://www.launchpad.net/cardapio',
	requires     = ['gtk', 'gtk.glade', 'gio', 'glib', 'gmenu', 'keybinder', 'gnomeapplet', 'dbus', 'dbus.service', 'dbus.mainloop.glib', 'xdg', 'gnome', 'simplejson', ],
	package_dir  = {'cardapio': 'src'},
	packages     = ['cardapio'],
	package_data = {'cardapio': package_data},
	scripts      = ['src/cardapio'],
	data_files   = data_files,
)
