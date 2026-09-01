import datetime
import logging
import os
import os.path as osp
from glob import glob


COLORS = {
    "WARNING": "yellow",
    "INFO": "white",
    "DEBUG": "blue",
    "CRITICAL": "red",
    "ERROR": "red",
}
ANSI_CODES = {
    'grey': 30,
    'red': 31,
    'green': 32,
    'yellow': 33,
    'blue': 34,
    'magenta': 35,
    'cyan': 36,
    'white': 37,
}
ANSI_ATTRS = {
    'bold': 1,
}


def _colored(text, color=None, attrs=None):
    """Return text wrapped in ANSI SGR escapes.

    This mirrors the small ANSI coloring subset used by the logger.

    >>> _colored('ok', color='red', attrs=['bold'])
    '\\x1b[1;31mok\\x1b[0m'
    >>> _colored('ok', color=None, attrs=None)
    'ok'
    """

    codes = []
    for attr in attrs or ():
        code = ANSI_ATTRS.get(attr)
        if code is not None:
            codes.append(str(code))
    code = ANSI_CODES.get(color)
    if code is not None:
        codes.append(str(code))
    if not codes:
        return str(text)
    return f'\033[{";".join(codes)}m{text}\033[0m'


class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt, use_color=True):
        logging.Formatter.__init__(self, fmt)
        self.use_color = use_color

    def format(self, record):
        levelname = record.levelname
        if self.use_color and levelname in COLORS:

            def colored(text):
                return _colored(
                    text,
                    color=COLORS[levelname],
                    attrs={"bold": True},
                )

            record.levelname2 = colored("{:<7}".format(record.levelname))
            record.message2 = colored(record.getMessage())

            asctime2 = datetime.datetime.fromtimestamp(record.created)
            record.asctime2 = _colored(asctime2, color="green")

            record.module2 = _colored(record.module, color="cyan")
            record.funcName2 = _colored(record.funcName, color="cyan")
            record.lineno2 = _colored(record.lineno, color="cyan")
        else:
            record.levelname2 = "{:<7}".format(record.levelname)
            record.message2 = record.getMessage()
            record.asctime2 = str(datetime.datetime.fromtimestamp(record.created))
            record.module2 = record.module
            record.funcName2 = record.funcName
            record.lineno2 = str(record.lineno)
        return logging.Formatter.format(self, record)

FORMAT = (
    "[%(levelname2)s] %(module2)s:%(funcName2)s:%(lineno2)s - %(message2)s"
)

class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            self.stream.write(msg + self.terminator)
            self.flush()
        except OSError:
            pass
        except Exception:
            self.handleError(record)


class ColoredLogger(logging.Logger):

    def __init__(self, name):
        import sys
        logging.Logger.__init__(self, name, logging.WARNING)

        use_color = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
        color_formatter = ColoredFormatter(FORMAT, use_color=use_color)

        console = SafeStreamHandler(sys.stdout)
        console.setFormatter(color_formatter)

        self.addHandler(console)
        return


def setup_logging(logfile_dir: str, max_num_logs=14):

    if not osp.exists(logfile_dir):
        os.makedirs(logfile_dir)
    else:
        old_logs = glob(osp.join(logfile_dir, '*.log'))
        old_logs.sort()
        n_log = len(old_logs)
        if n_log >= max_num_logs:
            to_remove = n_log - max_num_logs + 1
            try:
                for ii in range(to_remove):
                    os.remove(old_logs[ii])
            except Exception as e:
                logger.error(e)

    logfilename = datetime.datetime.now().strftime('_%Y_%m_%d-%H_%M_%S.log')
    logfilep = osp.join(logfile_dir, logfilename)
    fh = logging.FileHandler(logfilep, mode='w', encoding='utf-8')
    fh.setFormatter(
        logging.Formatter(
            ("[%(levelname)s] %(module)s:%(funcName)s:%(lineno)s - %(message)s")
        )
    )
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)
    _enable_faulthandler(fh, logfilep)


def _enable_faulthandler(file_handler: logging.FileHandler, logfile_path: str):
    try:
        import faulthandler
    except ImportError:
        return

    try:
        if faulthandler.is_enabled():
            faulthandler.disable()
        # faulthandler writes directly to the file stream on native crashes,
        # bypassing logging formatters but staying in the same timestamped log.
        faulthandler.enable(file=file_handler.stream, all_threads=True)
        logger.info(f'Native crash traces enabled in log file: {logfile_path}')
    except Exception as e:
        logger.warning(f'Failed to enable native crash traces: {e}')


logging.setLoggerClass(ColoredLogger)
logger = logging.getLogger('BallonTranslator')
logger.setLevel(logging.DEBUG)
logger.propagate = False

import sys
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception
