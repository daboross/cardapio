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

