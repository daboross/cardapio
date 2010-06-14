from distutils.core import setup
import os


# automatically build package_data by traversing folders

package_data = ['cardapio.ui']

os.chdir('cardapio')

for root, dir, files in os.walk('locale'):
	for file_ in files:
		if len(file_) > 3 and file_[-3:] == '.mo':
			package_data.append(os.path.join(root, file_))

for root, dir, files in os.walk('plugins'):
	for file_ in files:
		if len(file_) > 3 and file_[-3:] == '.py':
			package_data.append(os.path.join(root, file_))

os.chdir('..')


# install

setup(
	name         = 'Cardapio',
	version      = '0.9.101',
	description  = 'A menu with search capabilities.',
	author       = 'Thiago Teixeira',
	author_email = 'tvst@hotmail.com',
	url          = 'https://www.launchpad.net/cardapio',
	packages     = ['cardapio'],
	package_data = {'cardapio': package_data},
	data_files   = [
			('/usr/local/bin', ['cardapio/cardapio']),
			('/usr/lib/bonobo/servers', ['cardapio/cardapio.server']),
		],
	)

