# Thanks to rawktron
# https://github.com/ActiveState/code/blob/master/recipes/Python/572182_how_to_implement_kbhit_on_Linux/recipe-572182.py
# Mirror:  https://cgi.cse.unsw.edu.au/~z5214048/s.php/?572182 
# The code was OOP-icised and adapted for Python 3 (Thanks COMP 1531)

import sys, termios, atexit
from select import select
from abc import ABC, abstractmethod

# Base Class
class msvcrt_clone(ABC):
	def __init__(self):
		# save the terminal settings
		self._fd = sys.stdin.fileno()
		self._new_term = termios.tcgetattr(self._fd)
		self._old_term = termios.tcgetattr(self._fd)
		
		# new terminal setting unbuffered
		self._new_term[3] = (self._new_term[3] & ~termios.ICANON & ~termios.ECHO)
		
	@property
	def fd(self):
		return self._fd
	
	@property
	def old_term(self):
		return self._old_term
	
	@property
	def new_term(self):
		return self._new_term

	@fd.setter
	def fd(self, fd):
		self._fd = fd
		
	@old_term.setter
	def old_term(self, old_term):
		self._old_term = old_term

	@new_term.setter
	def new_term(self, new_term):
		self._fd = new_term


	# switch to normal terminal
	def set_normal_term():
		termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.old_term)

	# switch to unbuffered terminal
	def set_curses_term():
		termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.new_term)

	def putch(ch):
		sys.stdout.write(ch)

	def getch():
		return sys.stdin.read(1)

	def getche():
		ch = getch()
		putch(ch)
		return ch

	def kbhit():
		dr,dw,de = select([sys.stdin], [], [], 0)
		return dr != []

	# if run directly
	if __name__ == '__main__':
		atexit.register(set_normal_term)
		set_curses_term()

		while 1:
			if kbhit():
				ch = getch()
				break
			sys.stdout.write('.')

		print('done')
