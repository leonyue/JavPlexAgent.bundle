# coding=utf-8
from termcolor import colored


# noinspection PyPep8Naming,PyClassHasNoInit
class Log:
    """
    The Log API allows the developer to add their own messages to the plug-in’s log file. The different methods
    represent the different log levels available, in increasing levels of severity. The first argument to each method
    should be a format string, which is formatted using any additional arguments and keyword arguments provided.
    """

    @staticmethod
    def Debug(fmt, *args, **kwargs):
        """
        :type fmt: str | unicode
        """
        print colored("[D]", 'magenta'),
        print fmt

    @staticmethod
    def Info(fmt, *args, **kwargs):
        """
        :type fmt: str | unicode
        """
        print colored("[I]"),
        print fmt

    @staticmethod
    def Warn(fmt, *args, **kwargs):
        """
        :type fmt: str | unicode
        """
        print colored("[W]", 'yellow'),
        print fmt

    @staticmethod
    def Error(fmt, *args, **kwargs):
        """
        :type fmt: str | unicode
        """
        print colored("[E]", 'red'),
        print fmt

    @staticmethod
    def Critical(fmt, *args, **kwargs):
        """
        :type fmt: str | unicode
        """
        print colored("[C]", 'white', 'on_yellow'),
        print fmt

    @staticmethod
    def Exception(fmt, *args, **kwargs):
        """
        :type fmt: str | unicode
        """
        print colored("[E]", 'white', 'on_red'),
        print fmt
